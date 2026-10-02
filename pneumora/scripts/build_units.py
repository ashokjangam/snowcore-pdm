"""Cache 5-minute feature frames for every MetroPT unit used in the leave-one-unit-out study."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "autoresearch"))
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_metropt import build_features, normalise_name  # noqa: E402
from leak_physics import physics_features  # noqa: E402
from pneumora.contracts import ANALOG_SIGNALS, DIGITAL_SIGNALS  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
UNITS = PROCESSED / "units"
EXTERNAL = ROOT / "data" / "raw" / "external"
SOURCES = {
    "METROPT_2022_ZENODO_6854240": EXTERNAL / "metropt2022_train.csv",
    "METROPT2_ZENODO_7766691": EXTERNAL / "MetroPT2.csv",
}
SIGNALS = ANALOG_SIGNALS + DIGITAL_SIGNALS


def read_external(path: Path) -> pd.DataFrame:
    header = pd.read_csv(path, nrows=0).columns
    mapping = {column: normalise_name(column) for column in header}
    keep = [column for column, name in mapping.items() if name in ("timestamp",) + SIGNALS]
    pieces = []
    for chunk in pd.read_csv(path, usecols=keep, chunksize=2_000_000, low_memory=False):
        chunk = chunk.rename(columns=mapping)
        chunk["timestamp"] = pd.to_datetime(chunk["timestamp"], errors="coerce")
        for column in SIGNALS:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce").astype("float32")
        pieces.append(chunk.dropna(subset=["timestamp"]))
    return pd.concat(pieces).sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def unit_frame(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.copy()
    if "failure_active" not in raw:
        raw["failure_active"] = 0
        raw["minutes_to_failure"] = np.nan
    features = build_features(raw)
    return features.merge(physics_features(raw), on="timestamp", how="left")


def main() -> int:
    UNITS.mkdir(parents=True, exist_ok=True)
    metropt3 = pd.read_parquet(PROCESSED / "telemetry.parquet")
    unit_frame(metropt3).to_parquet(UNITS / "METROPT3_UCI_791.parquet", index=False)
    print("METROPT3_UCI_791 done")
    for name, path in SOURCES.items():
        unit_frame(read_external(path)).to_parquet(UNITS / f"{name}.parquet", index=False)
        print(name, "done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
