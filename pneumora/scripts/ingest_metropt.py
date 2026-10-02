"""Ingest and audit the official UCI MetroPT-3 archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pneumora.contracts import (  # noqa: E402
    ANALOG_SIGNALS,
    DERIVED,
    DIGITAL_SIGNALS,
    FAILURES,
    OBSERVED,
    SOURCE_DATASET,
    SOURCE_DOI,
)

RAW_ZIP = ROOT / "data" / "raw" / "metropt3.zip"
PROCESSED = ROOT / "data" / "processed"

ALIASES = {
    "timestamp": "timestamp",
    "unnamed_0": "row_id",
    "tp2": "tp2",
    "tp3": "tp3",
    "h1": "h1",
    "dv_pressure": "dv_pressure",
    "reservoirs": "reservoirs",
    "oil_temperature": "oil_temperature",
    "oil_temp": "oil_temperature",
    "motor_current": "motor_current",
    "comp": "comp",
    "dv_eletric": "dv_electric",
    "dv_electric": "dv_electric",
    "towers": "towers",
    "mpg": "mpg",
    "lps": "lps",
    "pressure_switch": "pressure_switch",
    "oil_level": "oil_level",
    "caudal_impulses": "caudal_impulses",
}


def normalise_name(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return ALIASES.get(value, value)


def locate_csv(archive: zipfile.ZipFile) -> str:
    csvs = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    if not csvs:
        raise ValueError("Official archive contains no CSV")
    return max(csvs, key=lambda name: archive.getinfo(name).file_size)


def read_source(path: Path) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        raise FileNotFoundError(f"Download the official UCI archive to {path}")
    with zipfile.ZipFile(path) as archive:
        member = locate_csv(archive)
        with archive.open(member) as handle:
            frame = pd.read_csv(handle, low_memory=False)
    frame.columns = [normalise_name(column) for column in frame.columns]
    if "timestamp" not in frame:
        raise ValueError(f"Timestamp column missing; found {list(frame.columns)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    frame = frame.drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    required = set(ANALOG_SIGNALS + DIGITAL_SIGNALS)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"MetroPT-3 signals missing: {sorted(missing)}")
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["data_origin"] = OBSERVED
    frame["source_dataset"] = SOURCE_DATASET
    return frame, member


def failure_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "episode_id": event.episode_id,
                "start": pd.Timestamp(event.start),
                "end": pd.Timestamp(event.end),
                "report": event.report,
                "onset_precision": event.onset_precision,
                "data_origin": OBSERVED,
                "source_dataset": SOURCE_DATASET,
            }
            for event in FAILURES
        ]
    )


def label_observed(frame: pd.DataFrame, failures: pd.DataFrame) -> pd.DataFrame:
    active = np.zeros(len(frame), dtype=np.int8)
    next_minutes = np.full(len(frame), np.nan)
    timestamps = frame["timestamp"].to_numpy(dtype="datetime64[ns]")
    for event in failures.itertuples():
        start = np.datetime64(event.start)
        end = np.datetime64(event.end)
        active[(timestamps >= start) & (timestamps <= end)] = 1
        delta = (start - timestamps) / np.timedelta64(1, "m")
        valid = (delta >= 0) & ((np.isnan(next_minutes)) | (delta < next_minutes))
        next_minutes[valid] = delta[valid]
    result = frame.copy()
    result["failure_active"] = active
    result["minutes_to_failure"] = next_minutes
    return result


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    indexed = frame.set_index("timestamp")
    analog = list(ANALOG_SIGNALS)
    digital = list(DIGITAL_SIGNALS)
    base = pd.concat(
        [
            indexed[analog].resample("5min").mean(),
            indexed[digital].resample("5min").mean(),
        ],
        axis=1,
    )
    pieces: list[pd.DataFrame] = []
    for minutes in (30, 120):
        periods = minutes // 5
        rolled = base[analog].rolling(periods, min_periods=max(2, periods // 2))
        stats = rolled.agg(["mean", "std", "min", "max"])
        stats.columns = [f"{name}_{stat}_{minutes}m" for name, stat in stats.columns]
        slopes = (base[analog] - base[analog].shift(periods)) / periods
        slopes.columns = [f"{name}_slope_{minutes}m" for name in slopes]
        states = base[digital].rolling(periods, min_periods=1).mean()
        states.columns = [f"{name}_fraction_{minutes}m" for name in states]
        pieces.extend([stats, slopes, states])
    features = pd.concat(pieces, axis=1)
    sampled = indexed.resample("5min").last()
    features["tp3_reservoir_gap"] = sampled["tp3"] - sampled["reservoirs"]
    features["loaded_fraction_2h"] = features[["comp_fraction_120m", "mpg_fraction_120m"]].mean(axis=1)
    features["cycle_starts_2h"] = indexed["comp"].diff().gt(0).rolling("120min").sum().resample("5min").last()
    features["failure_active"] = sampled["failure_active"]
    features["minutes_to_failure"] = sampled["minutes_to_failure"]
    features["data_origin"] = DERIVED
    features["source_dataset"] = SOURCE_DATASET
    return features.reset_index().dropna(subset=["tp3_mean_30m"])


def audit(frame: pd.DataFrame, source_member: str, source_path: Path) -> dict:
    deltas = frame["timestamp"].diff().dropna().dt.total_seconds()
    physical = {
        column: {
            "min": float(frame[column].min()),
            "median": float(frame[column].median()),
            "max": float(frame[column].max()),
        }
        for column in ANALOG_SIGNALS
    }
    return {
        "source_dataset": SOURCE_DATASET,
        "source_doi": SOURCE_DOI,
        "source_member": source_member,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "rows": int(len(frame)),
        "started_at": frame["timestamp"].min().isoformat(),
        "ended_at": frame["timestamp"].max().isoformat(),
        "median_cadence_seconds": float(deltas.median()),
        "duplicate_timestamps_after_dedup": int(frame["timestamp"].duplicated().sum()),
        "missing_by_signal": {
            column: int(frame[column].isna().sum())
            for column in ANALOG_SIGNALS + DIGITAL_SIGNALS
        },
        "physical_ranges": physical,
        "failure_episodes": len(FAILURES),
        "notes": [
            "Cadence is measured from the downloaded file; published descriptions conflict.",
            "Failure intervals are administrative reports, not a supervised target column.",
            "The first episode has day-level onset precision.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=RAW_ZIP)
    parser.add_argument("--output", type=Path, default=PROCESSED)
    args = parser.parse_args()
    frame, member = read_source(args.source)
    failures = failure_table()
    labelled = label_observed(frame, failures)
    features = build_features(labelled)
    args.output.mkdir(parents=True, exist_ok=True)
    labelled.to_parquet(args.output / "telemetry.parquet", index=False)
    failures.to_parquet(args.output / "failure_episodes.parquet", index=False)
    features.to_parquet(args.output / "features_5m.parquet", index=False)
    report = audit(labelled, member, args.source)
    report["feature_rows"] = len(features)
    (args.output / "data_profile.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
