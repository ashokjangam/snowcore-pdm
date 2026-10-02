"""Export one chart-ready case per failure from the protocol v2 prediction study.

Each held-out compressor is replayed with the configuration chosen on the other
two (prediction_study.json), so the alerts drawn in the app are the alerts that
were scored. The replay must reproduce the study's first alert for every
failure or the export stops.
"""

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

from louo_study import calibrate, single_scores, sustained, unit_events  # noqa: E402
from official_study import REMOVAL_NEED_MINUTES, merged_alerts, score_events, smooth, unit_splits  # noqa: E402
from prediction_study import rolling_flags  # noqa: E402
from pneumora.contracts import MAX_FALSE_ALERTS_PER_HEALTHY_DAYS  # noqa: E402

UNITS_DIR = ROOT / "data" / "processed" / "units"
STUDY = ROOT / "autoresearch" / "prediction_study.json"
OUT = ROOT / "data" / "snowflake"
TS = "%Y-%m-%d %H:%M:%S"
BEFORE = pd.Timedelta(hours=12)
AFTER = pd.Timedelta(hours=3)
COMPRESSORS = {
    "METROPT3_UCI_791": ("A", "Compressor A · MetroPT-3 · 2020"),
    "METROPT_2022_ZENODO_6854240": ("B", "Compressor B · MetroPT 2022"),
    "METROPT2_ZENODO_7766691": ("C", "Compressor C · MetroPT-2"),
}


def parse(config: str) -> tuple[tuple[str, ...], int, int, str]:
    parts, s, p, mode = config.split("|")
    return tuple(parts.split("+")), int(s[1:]), int(p[1:]), mode


def replay(frame: pd.DataFrame, config: str) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Alert flags for the test period of one unit, built exactly as prediction_study.score_unit does."""
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    parts, s, p, mode = parse(config)
    train, fit_end, cal_end = unit_splits(frame)
    cal = ((frame["timestamp"] >= fit_end) & (frame["timestamp"] < cal_end)).to_numpy()
    test = (frame["timestamp"] >= cal_end).to_numpy()
    cal_ts = frame.loc[cal, "timestamp"].reset_index(drop=True)
    raw = single_scores(frame, train, fit_end)
    budget = MAX_FALSE_ALERTS_PER_HEALTHY_DAYS / len(parts)
    flags = np.zeros(int(test.sum()), dtype=bool)
    for family in parts:
        series = smooth(raw[family], s)
        if mode == "static":
            flags |= sustained(series[test], calibrate(cal_ts, series[cal], p, budget), p)
        else:
            flags |= rolling_flags(frame["timestamp"], series, cal, test, p, budget)
    scored = frame.loc[test].reset_index(drop=True)
    scored["alerting"] = flags
    scored["alarm_on"] = scored["lps_fraction_30m"].fillna(0).to_numpy() > 0
    return scored, merged_alerts(scored["timestamp"], flags)


def main() -> int:
    study = json.loads(STUDY.read_text(encoding="utf-8"))
    events = unit_events()
    cases, zoom = [], []
    for fold in study["folds"]:
        unit = fold["held_out"]
        letter, compressor = COMPRESSORS[unit]
        scored, alerts = replay(pd.read_parquet(UNITS_DIR / f"{unit}.parquet"), fold["chosen"])
        start, end = scored["timestamp"].min(), scored["timestamp"].max()
        unit_rows = [e for e in events[unit] if e.end > start]
        mine = score_events(alerts, unit_rows, start, end)["events"]
        alarm = score_events(merged_alerts(scored["timestamp"], scored["alarm_on"].to_numpy()), unit_rows, start, end)["events"]
        recorded = {row["event_id"]: row for row in fold["events"]}
        for event, row, lps in zip(unit_rows, mine, alarm):
            expected = recorded[event.event_id]
            if (row["caught_in_time"], row["first_alert"]) != (expected["caught_in_time"], expected["first_alert"]):
                raise SystemExit(f"Replay of {unit} {event.event_id} differs from prediction_study.json: {row} vs {expected}")
            cases.append({
                "case_id": f"{letter}-{event.event_id}",
                "unit": unit,
                "compressor": compressor,
                "event_id": event.event_id,
                "kind": event.kind,
                "start_ts": event.start.strftime(TS),
                "end_ts": event.end.strftime(TS),
                "last_useful_alert": (event.end - pd.Timedelta(minutes=REMOVAL_NEED_MINUTES)).strftime(TS),
                "predicted_in_time": row["caught_in_time"],
                "first_alert": row["first_alert"],
                "minutes_before_end": row["minutes_before_end"],
                "minutes_after_start": row["minutes_after_start"],
                "alarm_in_time": lps["caught_in_time"],
                "alarm_first": lps["first_alert"],
                "alarm_minutes_before_end": lps["minutes_before_end"],
                "config": fold["chosen"],
            })
            window = scored[(scored["timestamp"] >= event.start - BEFORE) & (scored["timestamp"] <= event.end + AFTER)]
            zoom.append(pd.DataFrame({
                "case_id": f"{letter}-{event.event_id}",
                "ts": window["timestamp"].dt.strftime(TS),
                "loaded_run_minutes": window["loaded_run_minutes"].round(2),
                "pressure": window["tp3_mean_30m"].round(3),
                "alerting": window["alerting"],
                "alarm_on": window["alarm_on"],
            }))
        print(unit, fold["chosen"], [(c["event_id"], c["predicted_in_time"]) for c in cases if c["compressor"] == compressor])
    tables = {"PREDICTION_CASES": pd.DataFrame(cases), "PREDICTION_ZOOM": pd.concat(zoom, ignore_index=True)}
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, frame in tables.items():
        path = OUT / f"{name.lower()}.csv.gz"
        frame.columns = [column.upper() for column in frame.columns]
        frame.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0})
        manifest[name] = {"file": path.name, "rows": len(frame), "columns": list(frame.columns),
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print({name: len(frame) for name, frame in tables.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
