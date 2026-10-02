"""One-shot external test of the frozen official-protocol detector on MetroPT 2022 and MetroPT-2."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "autoresearch"))
sys.path.insert(0, str(ROOT / "scripts"))

from ingest_metropt import normalise_name  # noqa: E402
from leak_physics import physics_features  # noqa: E402
from official_study import (  # noqa: E402
    Event,
    alert_times,
    lps_alerts,
    parse_config,
    run_unit,
    score_events,
    unit_splits,
)
from pneumora.contracts import MAX_FALSE_ALERTS_PER_HEALTHY_DAYS  # noqa: E402

FREEZE = ROOT / "autoresearch" / "official_freeze.json"
OUTPUT = ROOT / "autoresearch" / "external_result.json"
EXTERNAL = ROOT / "data" / "raw" / "external"
SOURCES = {
    "METROPT_2022_ZENODO_6854240": EXTERNAL / "metropt2022_train.csv",
    "METROPT2_ZENODO_7766691": EXTERNAL / "MetroPT2.csv",
}
NEEDED = ("timestamp", "tp3", "comp", "lps")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def load_unit(path: Path) -> tuple[pd.DataFrame, dict]:
    header = pd.read_csv(path, nrows=0).columns
    mapping = {column: normalise_name(column) for column in header}
    keep = [column for column, name in mapping.items() if name in NEEDED]
    pieces = []
    for chunk in pd.read_csv(path, usecols=keep, chunksize=2_000_000, low_memory=False):
        chunk = chunk.rename(columns=mapping)
        chunk["timestamp"] = pd.to_datetime(chunk["timestamp"], errors="coerce")
        for column in ("tp3", "comp", "lps"):
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce").astype("float32")
        pieces.append(chunk.dropna(subset=["timestamp"]))
    raw = pd.concat(pieces).sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    frame = physics_features(raw)
    lps = raw.set_index("timestamp")["lps"].resample("5min").mean()
    frame["lps_fraction_30m"] = lps.rolling(6, min_periods=1).mean().reindex(frame["timestamp"]).to_numpy()
    profile = {
        "columns": list(header),
        "rows": int(len(raw)),
        "started_at": str(raw["timestamp"].min()),
        "ended_at": str(raw["timestamp"].max()),
        "median_cadence_seconds": float(raw["timestamp"].diff().dt.total_seconds().median()),
    }
    return frame, profile


def main() -> int:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    family, mode, bins, persistence = parse_config(freeze["detector"])
    units = {}
    pooled = {"false_alerts": 0, "healthy_days": 0.0, "probs": [], "air_caught": 0, "air_scored": 0, "lps_air_caught": 0}
    margins, lps_margins = [], []
    for source, path in SOURCES.items():
        frame, profile = load_unit(path)
        events = [
            Event(e["event_id"], pd.Timestamp(e["start"]), pd.Timestamp(e["end"]), e["kind"])
            for e in freeze["external_events"][source]
        ]
        result = run_unit(frame, events, [(family, mode, bins, persistence)])
        detector = result["configs"][freeze["detector"]]
        lps = result["lps_existing_alarm"]
        _, fit_end, cal_end = unit_splits(frame.sort_values("timestamp"))
        fit_duty = float(frame.loc[frame["timestamp"] < fit_end, "duty_30m"].mean())
        test = frame[frame["timestamp"] >= cal_end].sort_values("timestamp").reset_index(drop=True)
        transferred = score_events(
            alert_times(test["timestamp"], test["loaded_run_minutes"].fillna(0).to_numpy(), freeze["development_threshold_minutes"], persistence),
            [e for e in events if e.event_id in result["events_scored"]],
            test["timestamp"].min(),
            test["timestamp"].max(),
        )
        test_days = (test["timestamp"].max() - test["timestamp"].min()).total_seconds() / 86400
        rate = detector["merged_alerts"] / max(test_days * 1440, 1)
        for row in detector["events"]:
            window = (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).total_seconds() / 60
            pooled["probs"].append(1 - np.exp(-rate * max(window, 0)))
            if row["kind"] == "air_leak":
                pooled["air_scored"] += 1
                pooled["air_caught"] += int(row["caught_in_time"])
                if row["caught_in_time"]:
                    margins.append(row["minutes_before_end"])
        for row in lps["events"]:
            if row["kind"] == "air_leak" and row["caught_in_time"]:
                pooled["lps_air_caught"] += 1
                lps_margins.append(row["minutes_before_end"])
        pooled["false_alerts"] += detector["false_alerts"]
        pooled["healthy_days"] += detector["healthy_days"]
        units[source] = {
            "source_sha256": sha256(path),
            "profile": profile,
            "fit_window_loaded_duty": fit_duty,
            "windows": {k: result[k] for k in ("fit_window", "calibration_window", "test_window")},
            "events_scored": result["events_scored"],
            "events_excluded_before_calibration_end": [e.event_id for e in events if e.event_id not in result["events_scored"]],
            "detector": detector,
            "lps_existing_alarm": lps,
            "transferred_threshold_detector": transferred,
        }
    dist = np.array([1.0])
    for p in pooled["probs"]:
        dist = np.convolve(dist, [1 - p, p])
    total_caught = sum(r["caught_in_time"] for u in units.values() for r in u["detector"]["events"])
    null_p = float(dist[total_caught:].sum())
    false_rate = pooled["false_alerts"] / max(pooled["healthy_days"], 1e-9)
    median_margin = float(np.median(margins)) if margins else 0.0
    lps_margin = float(np.median(lps_margins)) if lps_margins else 0.0
    gates = {
        "air_leaks_caught_in_time": pooled["air_caught"] >= 2,
        "pooled_false_alerts_per_healthy_day": false_rate <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS,
        "beats_existing_lps_alarm_on_air_leaks": pooled["air_caught"] > pooled["lps_air_caught"]
        or (pooled["air_caught"] == pooled["lps_air_caught"] and median_margin >= lps_margin + 30),
        "random_alerter_null_all_events": null_p < 0.05,
    }
    report = {
        "study": "PNEUMORA frozen detector, one-shot external test",
        "detector": freeze["detector"],
        "units": units,
        "pooled": {
            "air_leaks_scored": pooled["air_scored"],
            "air_leaks_caught_in_time": pooled["air_caught"],
            "lps_air_leaks_caught_in_time": pooled["lps_air_caught"],
            "all_events_caught_in_time": total_caught,
            "false_alerts": pooled["false_alerts"],
            "healthy_days": pooled["healthy_days"],
            "false_alerts_per_healthy_day": false_rate,
            "median_minutes_before_end_air": median_margin,
            "random_alerter_expected_catches": float(sum(pooled["probs"])),
            "random_alerter_p_at_least_observed": null_p,
        },
        "gates": gates,
        "status": "PROMOTED" if all(gates.values()) else "NO_PROMOTION",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("pooled", "gates", "status")}, indent=2))
    for source, unit in units.items():
        print(source, unit["profile"]["started_at"], unit["profile"]["ended_at"], "duty", round(unit["fit_window_loaded_duty"], 3),
              "excluded", unit["events_excluded_before_calibration_end"])
        for row in unit["detector"]["events"]:
            print("  ", row["event_id"], row["kind"], row["caught_in_time"], row["minutes_after_start"], row["minutes_before_end"])
        print("   false/day", round(unit["detector"]["false_alerts_per_healthy_day"], 3), "LPS caught",
              unit["lps_existing_alarm"]["caught_in_time"], "transferred caught", unit["transferred_threshold_detector"]["caught_in_time"],
              "transferred false/day", round(unit["transferred_threshold_detector"]["false_alerts_per_healthy_day"], 3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
