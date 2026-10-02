"""Synthetic-trained leak model, scored once on the nine real MetroPT failures.

Training uses only label-free data: healthy fit-window rows from each unit plus
physics-based synthetic leak episodes injected into those rows
(SYNTHETIC_TRAINING_ONLY). No real failure interval is used to train or
calibrate. One configuration and the gates below are declared before scoring.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "autoresearch"))

from louo_study import unit_events  # noqa: E402
from official_study import alert_times, calibrate, merged_alerts, score_events, unit_splits  # noqa: E402
from pneumora.contracts import MAX_FALSE_ALERTS_PER_HEALTHY_DAYS, SYNTHETIC_TRAINING  # noqa: E402

UNITS_DIR = ROOT / "data" / "processed" / "units"
OUTPUT = ROOT / "autoresearch" / "synthetic_model_study.json"
FEATURES = ["loaded_run", "duty30", "duty60", "gain30n", "gain60n", "drop60n", "oil_delta", "current_load"]
PERSISTENCE_BINS = 6
EPISODES_PER_UNIT = 400
GATES = {
    "caught_beats_lps": "catches > LPS catches on the nine real failures, or equal with >= 30 min more median margin",
    "air_leaks_not_worse_than_lps": "air-leak catches >= LPS air-leak catches",
    "false_alert_budget": "pooled false alerts per healthy day <= 1/7",
    "random_null": "random alerter at the same rate matches the catches with p < 0.05",
    "beats_wrong_physics_control": "catches > wrong-physics control catches",
}


def unit_baseline(fit: pd.DataFrame) -> dict:
    working = fit[fit["duty_60m"] > 0.2]
    current = fit["motor_current_mean_30m"].dropna()
    return {
        "gain": max(float(working["loaded_gain_rate_60m"].median()), 1e-3),
        "drop": max(float(fit["idle_drop_rate_60m"].median()), 1e-3),
        "oil": float(fit["oil_temperature_mean_30m"].median()),
        "current_idle": float(current.quantile(0.2)),
        "current_loaded": float(current.quantile(0.95)),
    }


def normalise(frame: pd.DataFrame, base: dict) -> pd.DataFrame:
    span = max(base["current_loaded"] - base["current_idle"], 1e-3)
    return pd.DataFrame(
        {
            "loaded_run": frame["loaded_run_minutes"].fillna(0).clip(0, 240),
            "duty30": frame["duty_30m"],
            "duty60": frame["duty_60m"],
            "gain30n": frame["loaded_gain_rate_30m"] / base["gain"],
            "gain60n": frame["loaded_gain_rate_60m"] / base["gain"],
            "drop60n": frame["idle_drop_rate_60m"] / base["drop"],
            "oil_delta": frame["oil_temperature_mean_30m"] - base["oil"],
            "current_load": (frame["motor_current_mean_30m"] - base["current_idle"]) / span,
        },
        index=frame.index,
    )


def synthetic_leaks(healthy: pd.DataFrame, rng: np.random.Generator, wrong_physics: bool) -> pd.DataFrame:
    rows = []
    for _ in range(EPISODES_PER_UNIT):
        length = int(rng.integers(6, 73))
        start = int(rng.integers(0, max(len(healthy) - length, 1)))
        block = healthy.iloc[start:start + length].copy().reset_index(drop=True)
        severity = rng.uniform(0.3, 1.0)
        continuous = severity > 0.55
        oil_rise = rng.uniform(2, 10) * severity
        for k in range(len(block)):
            ramp = min(1.0, (k + 1) / 6)
            if wrong_physics:
                block.loc[k, "loaded_run"] = rng.uniform(0.5, 3)
                block.loc[k, ["duty30", "duty60"]] = rng.uniform(0.02, 0.15)
                block.loc[k, ["gain30n", "gain60n"]] = 1 + rng.uniform(0.3, 1.5) * severity
                block.loc[k, "drop60n"] = rng.uniform(0.2, 0.9)
                block.loc[k, "oil_delta"] -= oil_rise * ramp
                block.loc[k, "current_load"] = rng.uniform(-0.2, 0.2)
                continue
            block.loc[k, "loaded_run"] = min(240, 5 * (k + 1)) if continuous else rng.uniform(4, 25) * severity
            duty = block.loc[k, "duty60"] if pd.notna(block.loc[k, "duty60"]) else 0.15
            target = 0.97 if continuous else 0.5 + 0.4 * severity
            block.loc[k, ["duty30", "duty60"]] = duty + (target - duty) * ramp + rng.normal(0, 0.02)
            block.loc[k, ["gain30n", "gain60n"]] = max(0.0, 1 - 0.95 * severity * ramp + rng.normal(0, 0.05))
            block.loc[k, "drop60n"] = np.nan if continuous else 1 + 9 * severity * ramp
            block.loc[k, "oil_delta"] = block.loc[k, "oil_delta"] + oil_rise * (k + 1) / len(block)
            block.loc[k, "current_load"] = 0.8 + 0.2 * rng.random()
        rows.append(block)
    out = pd.concat(rows, ignore_index=True)
    out["label"] = 1
    out["data_origin"] = SYNTHETIC_TRAINING
    return out


def train(units: dict, wrong_physics: bool) -> HistGradientBoostingClassifier:
    rng = np.random.default_rng(20261001 + int(wrong_physics))
    parts = []
    for unit in units.values():
        healthy = unit["x"][unit["fit_mask"]].dropna(subset=["loaded_run"])
        negatives = healthy.copy()
        negatives["label"] = 0
        parts += [negatives, synthetic_leaks(healthy, rng, wrong_physics)]
    data = pd.concat(parts, ignore_index=True)
    model = HistGradientBoostingClassifier(max_depth=4, max_iter=200, learning_rate=0.05, random_state=42)
    model.fit(data[FEATURES], data["label"])
    return model


def score(units: dict, events: dict, model) -> dict:
    per_unit, pooled_rows, false_alerts, healthy_days, probs = {}, [], 0, 0.0, []
    for name, unit in units.items():
        proba = model.predict_proba(unit["x"][FEATURES])[:, 1]
        threshold = calibrate(unit["cal_ts"], proba[unit["cal_mask"]], PERSISTENCE_BINS)
        alerts = alert_times(unit["test_ts"], proba[unit["test_mask"]], threshold, PERSISTENCE_BINS)
        scored = [e for e in events[name] if e.end > unit["test_ts"].min()]
        result = score_events(alerts, scored, unit["test_ts"].min(), unit["test_ts"].max())
        result["threshold"] = float(threshold)
        per_unit[name] = result
        pooled_rows += result["events"]
        false_alerts += result["false_alerts"]
        healthy_days += result["healthy_days"]
        rate = result["merged_alerts"] / max(unit["test_days"] * 1440, 1)
        for row in result["events"]:
            window = (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).total_seconds() / 60
            probs.append(1 - np.exp(-rate * max(window, 0)))
    dist = np.array([1.0])
    for p in probs:
        dist = np.convolve(dist, [1 - p, p])
    caught = sum(r["caught_in_time"] for r in pooled_rows)
    margins = [r["minutes_before_end"] for r in pooled_rows if r["caught_in_time"]]
    return {
        "per_unit": per_unit,
        "caught": caught,
        "air_caught": sum(r["caught_in_time"] for r in pooled_rows if r["kind"] == "air_leak"),
        "events": len(pooled_rows),
        "false_alerts": false_alerts,
        "false_per_day": false_alerts / max(healthy_days, 1e-9),
        "median_margin": float(np.median(margins)) if margins else 0.0,
        "null_p": float(dist[caught:].sum()),
    }


def lps_baseline(units: dict, events: dict) -> dict:
    rows, false_alerts, healthy_days = [], 0, 0.0
    for name, unit in units.items():
        flags = unit["frame"].loc[unit["test_mask"], "lps_fraction_30m"].fillna(0).to_numpy() > 0
        scored = [e for e in events[name] if e.end > unit["test_ts"].min()]
        result = score_events(merged_alerts(unit["test_ts"], flags), scored, unit["test_ts"].min(), unit["test_ts"].max())
        rows += result["events"]
        false_alerts += result["false_alerts"]
        healthy_days += result["healthy_days"]
    margins = [r["minutes_before_end"] for r in rows if r["caught_in_time"]]
    return {
        "caught": sum(r["caught_in_time"] for r in rows),
        "air_caught": sum(r["caught_in_time"] for r in rows if r["kind"] == "air_leak"),
        "false_alerts": false_alerts,
        "false_per_day": false_alerts / max(healthy_days, 1e-9),
        "median_margin": float(np.median(margins)) if margins else 0.0,
    }


def main() -> int:
    events = unit_events()
    units = {}
    for name in events:
        frame = pd.read_parquet(UNITS_DIR / f"{name}.parquet").sort_values("timestamp").reset_index(drop=True)
        _, fit_end, cal_end = unit_splits(frame)
        fit_mask = (frame["timestamp"] < fit_end).to_numpy()
        cal_mask = ((frame["timestamp"] >= fit_end) & (frame["timestamp"] < cal_end)).to_numpy()
        test_mask = (frame["timestamp"] >= cal_end).to_numpy()
        test_ts = frame.loc[test_mask, "timestamp"].reset_index(drop=True)
        units[name] = {
            "frame": frame,
            "x": normalise(frame, unit_baseline(frame[fit_mask])),
            "fit_mask": fit_mask,
            "cal_mask": cal_mask,
            "test_mask": test_mask,
            "cal_ts": frame.loc[cal_mask, "timestamp"].reset_index(drop=True),
            "test_ts": test_ts,
            "test_days": (test_ts.max() - test_ts.min()).total_seconds() / 86400,
        }
    model = score(units, events, train(units, wrong_physics=False))
    control = score(units, events, train(units, wrong_physics=True))
    lps = lps_baseline(units, events)
    gates = {
        "caught_beats_lps": model["caught"] > lps["caught"]
        or (model["caught"] == lps["caught"] and model["median_margin"] >= lps["median_margin"] + 30),
        "air_leaks_not_worse_than_lps": model["air_caught"] >= lps["air_caught"],
        "false_alert_budget": model["false_per_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS,
        "random_null": model["null_p"] < 0.05,
        "beats_wrong_physics_control": model["caught"] > control["caught"],
    }
    report = {
        "study": "PNEUMORA synthetic-trained leak model, nine real failures",
        "declared_gates": GATES,
        "training": "Healthy fit-window rows of all three units plus SYNTHETIC_TRAINING_ONLY leak episodes; no real failure labels.",
        "caveat": "The generator encodes leak physics learned by inspecting MetroPT-3 failures, and all nine real failures were scored in earlier studies.",
        "model": model,
        "wrong_physics_control": control,
        "lps": lps,
        "gates": gates,
        "status": "PROMOTED" if all(gates.values()) else "NO_PROMOTION",
    }
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    summary = {k: {kk: v for kk, v in report[k].items() if kk != "per_unit"} for k in ("model", "wrong_physics_control", "lps")}
    print(json.dumps({**summary, "gates": gates, "status": report["status"]}, indent=2))
    for name, result in model["per_unit"].items():
        print(name, [(r["event_id"], r["caught_in_time"], r["minutes_after_start"]) for r in result["events"]], "false", result["false_alerts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
