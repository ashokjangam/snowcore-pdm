"""Leave-one-unit-out study across MetroPT-3, MetroPT 2022 and MetroPT-2.

Every configuration is scored per unit with the label-free recipe (fit 21 days,
calibrate 14 days). For each held-out unit the configuration is chosen on the
other two units only, then the held-out unit is scored. Gates are declared in
GATES before any result is computed and are written to the report unchanged.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "autoresearch"))

from official_study import (  # noqa: E402
    Event,
    adaptive_score,
    fit_family,
    merged_alerts,
    metropt3_events,
    raw_score,
    score_events,
    smooth,
    unit_splits,
)
from pneumora.contracts import MAX_FALSE_ALERTS_PER_HEALTHY_DAYS  # noqa: E402

UNITS_DIR = ROOT / "data" / "processed" / "units"
FREEZE = ROOT / "autoresearch" / "official_freeze.json"
OUTPUT = ROOT / "autoresearch" / "louo_study.json"

GATES = {
    "held_out_caught_beats_lps": "pooled held-out catches > LPS catches on the same events, or equal with >= 30 min more median margin",
    "held_out_air_leaks_not_worse_than_lps": "pooled held-out air-leak catches >= LPS air-leak catches",
    "held_out_false_alert_budget": "pooled held-out false alerts per healthy day <= 1/7",
    "held_out_random_null": "random alerter at the same rate matches the catches with p < 0.05",
}
SINGLE = ("loaded_run", "leak_w30", "leak_w60", "lps_loaded", "oil_residual", "pca_residual")
SMOOTHING = (1, 6)
PERSISTENCE = (3, 6, 12)
OIL_INPUTS = ("duty_30m", "duty_60m", "motor_current_mean_30m", "motor_current_mean_120m")


def unit_events() -> dict[str, list[Event]]:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    events = {"METROPT3_UCI_791": metropt3_events()}
    for unit, rows in freeze["external_events"].items():
        events[unit] = [Event(r["event_id"], pd.Timestamp(r["start"]), pd.Timestamp(r["end"]), r["kind"]) for r in rows]
    return events


def oil_design(frame: pd.DataFrame) -> np.ndarray:
    hour = frame["timestamp"].dt.hour + frame["timestamp"].dt.minute / 60
    base = frame[list(OIL_INPUTS)].fillna(0).to_numpy()
    return np.column_stack([base, np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)])


def single_scores(frame: pd.DataFrame, train: pd.DataFrame, fit_end: pd.Timestamp) -> dict[str, np.ndarray]:
    scores = {}
    for family in ("loaded_run", "leak_w30", "leak_w60"):
        scores[family] = raw_score(fit_family(family, train), frame)
    scores["lps_loaded"] = (frame["lps_fraction_30m"].fillna(0) * frame["duty_30m"].fillna(0)).to_numpy()
    usable = train.dropna(subset=["oil_temperature_mean_30m"])
    model = Ridge(alpha=1.0).fit(oil_design(usable), usable["oil_temperature_mean_30m"])
    residual = np.abs(frame["oil_temperature_mean_30m"].to_numpy() - model.predict(oil_design(frame)))
    norm = max(float(np.nanquantile(np.abs(usable["oil_temperature_mean_30m"] - model.predict(oil_design(usable))), 0.99)), 1e-6)
    scores["oil_residual"] = np.nan_to_num(residual / norm, nan=0.0)
    scores["pca_residual"] = np.nan_to_num(adaptive_score("pca_residual", frame, fit_end), nan=0.0)
    return scores


def sustained(scores: np.ndarray, threshold: float, persistence: int) -> np.ndarray:
    above = pd.Series(scores >= threshold)
    return above.rolling(persistence, min_periods=persistence).min().fillna(0).astype(bool).to_numpy()


def calibrate(timestamps: pd.Series, scores: np.ndarray, persistence: int, budget: float) -> float:
    days = max((timestamps.max() - timestamps.min()).total_seconds() / 86400, 1)
    finite = scores[np.isfinite(scores)]
    for threshold in np.unique(np.quantile(finite, np.linspace(0.90, 0.99995, 300))):
        if len(merged_alerts(timestamps, sustained(scores, threshold, persistence))) / days <= budget:
            return float(threshold)
    return float(np.nextafter(finite.max(), np.inf))


def configs() -> list[tuple[tuple[str, ...], int, int]]:
    rows = [((family,), s, p) for family in SINGLE for s in SMOOTHING for p in PERSISTENCE]
    pairs = [("loaded_run", "lps_loaded"), ("loaded_run", "oil_residual"), ("loaded_run", "lps_loaded", "oil_residual"),
             ("leak_w30", "lps_loaded"), ("loaded_run", "pca_residual")]
    rows += [(pair, s, p) for pair in pairs for s in SMOOTHING for p in PERSISTENCE]
    return rows


def name_of(parts: tuple[str, ...], s: int, p: int) -> str:
    return f"{'+'.join(parts)}|s{s}|p{p}"


def score_unit(frame: pd.DataFrame, events: list[Event]) -> dict:
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
    for parts, s, p in configs():
        budget = MAX_FALSE_ALERTS_PER_HEALTHY_DAYS / len(parts)
        flags = np.zeros(int(test.sum()), dtype=bool)
        for family in parts:
            series = smooth(raw[family], s)
            threshold = calibrate(cal_ts, series[cal], p, budget)
            flags |= sustained(series[test], threshold, p)
        results[name_of(parts, s, p)] = score_events(merged_alerts(test_ts, flags), scored, start, end)
    lps = frame.loc[test, "lps_fraction_30m"].fillna(0).to_numpy() > 0
    return {"results": results, "lps": score_events(merged_alerts(test_ts, lps), scored, start, end),
            "test_days": (end - start).total_seconds() / 86400}


def pooled(results: list[dict]) -> dict:
    rows = [row for result in results for row in result["events"]]
    false_alerts = sum(r["false_alerts"] for r in results)
    healthy = sum(r["healthy_days"] for r in results)
    margins = [r["minutes_before_end"] for r in rows if r["caught_in_time"]]
    return {
        "caught": sum(r["caught_in_time"] for r in rows),
        "air_caught": sum(r["caught_in_time"] for r in rows if r["kind"] == "air_leak"),
        "events": len(rows),
        "false_alerts": false_alerts,
        "false_per_day": false_alerts / max(healthy, 1e-9),
        "median_margin": float(np.median(margins)) if margins else 0.0,
    }


def rank(stats: dict) -> tuple:
    return (stats["false_per_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS, stats["caught"], -stats["false_per_day"], stats["median_margin"])


def null_p(fold_results: list[tuple[dict, float]]) -> tuple[float, float]:
    dist, expected, caught = np.array([1.0]), 0.0, 0
    for result, days in fold_results:
        rate = result["merged_alerts"] / max(days * 1440, 1)
        for row in result["events"]:
            window = (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).total_seconds() / 60
            prob = 1 - np.exp(-rate * max(window, 0))
            expected += prob
            dist = np.convolve(dist, [1 - prob, prob])
            caught += int(row["caught_in_time"])
    return float(dist[caught:].sum()), expected


def main() -> int:
    events = unit_events()
    units = {}
    for unit, unit_events_ in events.items():
        units[unit] = score_unit(pd.read_parquet(UNITS_DIR / f"{unit}.parquet"), unit_events_)
        print(unit, "scored", flush=True)
    names = list(next(iter(units.values()))["results"])
    folds, held_results, lps_results = [], [], []
    for held in units:
        training = [u for u in units if u != held]
        chosen = max(names, key=lambda n: rank(pooled([units[u]["results"][n] for u in training])))
        result = units[held]["results"][chosen]
        held_results.append((result, units[held]["test_days"]))
        lps_results.append(units[held]["lps"])
        folds.append({"held_out": held, "chosen": chosen, "train_stats": pooled([units[u]["results"][chosen] for u in training]),
                      "held_out_stats": pooled([result]), "lps_held_out_stats": pooled([units[held]["lps"]]),
                      "events": result["events"]})
    model = pooled([r for r, _ in held_results])
    lps = pooled(lps_results)
    p_value, expected = null_p(held_results)
    gates = {
        "held_out_caught_beats_lps": model["caught"] > lps["caught"]
        or (model["caught"] == lps["caught"] and model["median_margin"] >= lps["median_margin"] + 30),
        "held_out_air_leaks_not_worse_than_lps": model["air_caught"] >= lps["air_caught"],
        "held_out_false_alert_budget": model["false_per_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS,
        "held_out_random_null": p_value < 0.05,
    }
    everywhere = max(names, key=lambda n: rank(pooled([units[u]["results"][n] for u in units])))
    report = {
        "study": "PNEUMORA leave-one-unit-out detector study",
        "declared_gates": GATES,
        "caveat": "The physics families were designed after inspecting MetroPT-3 failures, and the external failures were seen once in the frozen test; this study is cross-validation, not an untouched test.",
        "folds": folds,
        "held_out_pooled": model,
        "lps_pooled_same_events": lps,
        "random_alerter": {"expected_catches": expected, "p_at_least_observed": p_value},
        "gates": gates,
        "status": "PROMOTED" if all(gates.values()) else "NO_PROMOTION",
        "deployment_config_if_promoted": everywhere,
        "deployment_config_all_units": pooled([units[u]["results"][everywhere] for u in units]),
        "leaderboard_all_units": sorted(
            ({"config": n, **pooled([units[u]["results"][n] for u in units])} for n in names),
            key=lambda row: (-(row["false_per_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS), -row["caught"], row["false_per_day"]),
        )[:20],
    }
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("held_out_pooled", "lps_pooled_same_events", "random_alerter", "gates", "status", "deployment_config_if_promoted")}, indent=2))
    for fold in folds:
        print(fold["held_out"], fold["chosen"], fold["held_out_stats"], "LPS", fold["lps_held_out_stats"])
        for row in fold["events"]:
            print("   ", row["event_id"], row["kind"], row["caught_in_time"], row["minutes_after_start"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
