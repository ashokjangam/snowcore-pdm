"""Protocol v2: predict the in-service air-leak failure, held out by compressor.

Target (the dataset owners' protocol, Veloso et al. 2022): an alert counts as a
prediction when it arrives at least two hours before the reported end of the
failure, the point by which the train must be taken out of service. Alerts up to
two hours before the reported start also count, so earlier warnings are not
punished as false.

Why a v2 exists: the leave-one-unit-out study (louo_study.py) passed every gate
except the false-alert budget, and its own leaderboard showed the oil-temperature
add-on drove those false alerts. v2 is written after seeing that result. It keeps
only air-leak physics (the product is an air-leak detector) and adds a
label-free rolling recalibration for operating drift. Gates below are fixed
before this file is run and are written to the report unchanged.

All nine failures have been seen by the designers. This is cross-validation
under a revised protocol, not an untouched test; no untouched MetroPT data exists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "autoresearch"))

from louo_study import calibrate, name_of, null_p, pooled, single_scores, sustained, unit_events  # noqa: E402
from official_study import merged_alerts, score_events, smooth, unit_splits  # noqa: E402
from pneumora.contracts import MAX_FALSE_ALERTS_PER_HEALTHY_DAYS  # noqa: E402

UNITS_DIR = ROOT / "data" / "processed" / "units"
OUTPUT = ROOT / "autoresearch" / "prediction_study.json"

GATES = {
    "air_predictions_beat_existing_alarm": "pooled held-out air leaks predicted > existing alarm's air leaks predicted on the same events",
    "no_fold_worse_than_existing_alarm": "on every held-out compressor, air leaks predicted >= existing alarm's",
    "false_alert_budget": "pooled held-out false alerts per healthy day <= 1/7",
    "beats_random_alerter": "random alerter at the same alert rate matches the predictions with p < 0.01",
    "useful_lead": "median warning before the train must be removed (reported end) >= 180 minutes",
}
FAMILIES = ("loaded_run", "leak_w30", "leak_w60", "lps_loaded")
PAIRS = (("loaded_run", "lps_loaded"), ("leak_w30", "lps_loaded"), ("loaded_run", "leak_w30"))
SMOOTHING = (1, 6)
PERSISTENCE = (3, 6, 12)
CALIBRATION = ("static", "rolling")
ROLLING_WINDOW_DAYS = 14
ROLLING_EVERY_DAYS = 7


def configs() -> list[tuple[tuple[str, ...], int, int, str]]:
    parts = [(f,) for f in FAMILIES] + list(PAIRS)
    return [(p, s, k, c) for p in parts for s in SMOOTHING for k in PERSISTENCE for c in CALIBRATION]


def label(parts: tuple[str, ...], s: int, p: int, mode: str) -> str:
    return f"{name_of(parts, s, p)}|{mode}"


def rolling_flags(timestamps: pd.Series, series: np.ndarray, cal_mask: np.ndarray, test_mask: np.ndarray,
                  persistence: int, budget: float) -> np.ndarray:
    """Recalibrate weekly on the trailing 14 days of the unit's own scores; no labels used."""
    ts = timestamps.reset_index(drop=True)
    test_idx = np.flatnonzero(test_mask)
    flags = np.zeros(len(test_idx), dtype=bool)
    above_all = None
    start = ts.iloc[test_idx[0]]
    week_starts = pd.date_range(start, ts.iloc[test_idx[-1]] + pd.Timedelta(days=ROLLING_EVERY_DAYS),
                                freq=f"{ROLLING_EVERY_DAYS}D")
    thresholds = np.empty(len(ts))
    thresholds[:] = np.nan
    for left, right in zip(week_starts, week_starts[1:]):
        window = ((ts >= left - pd.Timedelta(days=ROLLING_WINDOW_DAYS)) & (ts < left)).to_numpy()
        if window.sum() < 288:
            window = cal_mask
        threshold = calibrate(ts[window].reset_index(drop=True), series[window], persistence, budget)
        thresholds[((ts >= left) & (ts < right)).to_numpy()] = threshold
    above_all = series >= np.nan_to_num(thresholds, nan=np.inf)
    sustained_all = pd.Series(above_all).rolling(persistence, min_periods=persistence).min().fillna(0).astype(bool).to_numpy()
    flags[:] = sustained_all[test_idx]
    return flags


def score_unit(frame: pd.DataFrame, events) -> dict:
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    train, fit_end, cal_end = unit_splits(frame)
    cal = ((frame["timestamp"] >= fit_end) & (frame["timestamp"] < cal_end)).to_numpy()
    test = (frame["timestamp"] >= cal_end).to_numpy()
    cal_ts = frame.loc[cal, "timestamp"].reset_index(drop=True)
    test_ts = frame.loc[test, "timestamp"].reset_index(drop=True)
    start, end = test_ts.min(), test_ts.max()
    scored = [e for e in events if e.end > start]
    raw = single_scores(frame, train, fit_end)
    results = {}
    for parts, s, p, mode in configs():
        budget = MAX_FALSE_ALERTS_PER_HEALTHY_DAYS / len(parts)
        flags = np.zeros(int(test.sum()), dtype=bool)
        for family in parts:
            series = smooth(raw[family], s)
            if mode == "static":
                threshold = calibrate(cal_ts, series[cal], p, budget)
                flags |= sustained(series[test], threshold, p)
            else:
                flags |= rolling_flags(frame["timestamp"], series, cal, test, p, budget)
        results[label(parts, s, p, mode)] = score_events(merged_alerts(test_ts, flags), scored, start, end)
    lps = frame.loc[test, "lps_fraction_30m"].fillna(0).to_numpy() > 0
    return {"results": results, "lps": score_events(merged_alerts(test_ts, lps), scored, start, end),
            "test_days": (end - start).total_seconds() / 86400}


def rank(stats: dict) -> tuple:
    return (stats["false_per_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS, stats["air_caught"], -stats["false_per_day"],
            stats["median_margin"])


def main() -> int:
    events = unit_events()
    units = {}
    for unit, rows in events.items():
        units[unit] = score_unit(pd.read_parquet(UNITS_DIR / f"{unit}.parquet"), rows)
        print(unit, "scored", flush=True)
    names = list(next(iter(units.values()))["results"])
    folds, held, lps_rows = [], [], []
    for unit in units:
        training = [u for u in units if u != unit]
        chosen = max(names, key=lambda n: rank(pooled([units[u]["results"][n] for u in training])))
        result = units[unit]["results"][chosen]
        held.append((result, units[unit]["test_days"]))
        lps_rows.append(units[unit]["lps"])
        folds.append({"held_out": unit, "chosen": chosen,
                      "train_stats": pooled([units[u]["results"][chosen] for u in training]),
                      "held_out_stats": pooled([result]), "existing_alarm_held_out": pooled([units[unit]["lps"]]),
                      "events": result["events"]})
    model = pooled([r for r, _ in held])
    alarm = pooled(lps_rows)
    p_value, expected = null_p(held)
    pre_onset = sum(1 for f in folds for e in f["events"]
                    if e["caught_in_time"] and e["minutes_after_start"] is not None and e["minutes_after_start"] < 0)
    gates = {
        "air_predictions_beat_existing_alarm": model["air_caught"] > alarm["air_caught"],
        "no_fold_worse_than_existing_alarm": all(f["held_out_stats"]["air_caught"] >= f["existing_alarm_held_out"]["air_caught"]
                                                 for f in folds),
        "false_alert_budget": model["false_per_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS,
        "beats_random_alerter": p_value < 0.01,
        "useful_lead": model["median_margin"] >= 180,
    }
    everywhere = max(names, key=lambda n: rank(pooled([units[u]["results"][n] for u in units])))
    report = {
        "study": "PNEUMORA protocol v2: in-service air-leak failure prediction, leave one compressor out",
        "target": "alert from 2 h before reported start up to 2 h before reported end (train removal)",
        "declared_gates": GATES,
        "why_v2": "v1 (louo_study.py) failed only the false-alert budget; its leaderboard showed the oil-temperature add-on drove "
                  "the false alerts. v2 keeps air-leak physics only and adds label-free weekly recalibration.",
        "caveat": "Written after seeing v1. All nine failures had been seen by the designers. Cross-validation under a revised "
                  "protocol, not an untouched test; no untouched MetroPT data exists.",
        "folds": folds,
        "held_out_pooled": model,
        "existing_alarm_same_events": alarm,
        "pre_onset_predictions": pre_onset,
        "random_alerter": {"expected_catches": expected, "p_at_least_observed": p_value},
        "gates": gates,
        "status": "PROMOTED_CROSS_VALIDATED" if all(gates.values()) else "NO_PROMOTION",
        "deployment_config": everywhere,
        "deployment_config_all_units": pooled([units[u]["results"][everywhere] for u in units]),
        "deployment_events_all_units": [e for u in units for e in units[u]["results"][everywhere]["events"]],
        "leaderboard_all_units": sorted(
            ({"config": n, **pooled([units[u]["results"][n] for u in units])} for n in names),
            key=lambda row: (-(row["false_per_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS), -row["air_caught"], row["false_per_day"]),
        )[:15],
    }
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("held_out_pooled", "existing_alarm_same_events", "pre_onset_predictions",
                                             "random_alerter", "gates", "status", "deployment_config")}, indent=2))
    for fold in folds:
        print(fold["held_out"], fold["chosen"], fold["held_out_stats"], "ALARM", fold["existing_alarm_held_out"])
        for row in fold["events"]:
            print("   ", row["event_id"], row["kind"], row["caught_in_time"], row["minutes_after_start"], row["minutes_before_end"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
