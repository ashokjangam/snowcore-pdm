"""Can any approach warn before a MetroPT air or oil leak is reported?

Three compressors, nine real failures. Every arm is held out by compressor: a
label-free configuration is chosen on the other two units, and a supervised model
is trained only on the other two units' failures. Gates are declared in GATES
before any arm is scored and are written to the report unchanged.

Arms
- Label-free cycle physics: idle decay floor (leak-down), loaded rise, loaded
  minutes, cycle rate, oil and current, a combined leak index, multi-day EWMA drift
  and a three-day CUSUM.
- Supervised precursor model: gradient boosting on the six hours before the
  training units' failures.
- Onset-trained model: trained on the first two hours after training-unit onsets.
- Replay-augmented model: precursor labels plus SYNTHETIC_TRAINING_ONLY replays,
  real onset signatures from training units attenuated and added to healthy bins.

A separate leak-injection study adds a growing leak to real healthy cycles to
measure the smallest leak the frozen label-free arm detects.
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
sys.path.insert(0, str(ROOT / "scripts"))

from build_cycles import bin_features, inject_leak  # noqa: E402
from louo_study import unit_events  # noqa: E402
from official_study import Event, merged_alerts, unit_splits  # noqa: E402
from pneumora.contracts import MAX_FALSE_ALERTS_PER_HEALTHY_DAYS  # noqa: E402

UNITS_DIR = ROOT / "data" / "processed" / "units"
CYCLES_DIR = ROOT / "data" / "processed" / "cycles"
OUTPUT = ROOT / "autoresearch" / "precursor_study.json"

PRE_HOURS = 6
RELATED_BEFORE_HOURS = 24
OFFICIAL_NEED_MINUTES = 120
BUDGET = MAX_FALSE_ALERTS_PER_HEALTHY_DAYS
HOURS = (1, 6, 24)
PERSISTENCE = (1, 3, 6)
SUPERVISED_PERSISTENCE = 3
STALE_MINUTES = 60
SEED = 7

GATES = {
    "pre_onset_three_of_nine": "held-out warnings in [reported start - 6 h, reported start) >= 3 of 9",
    "false_alert_budget": "held-out false alerts per healthy day <= 1/7",
    "beats_random_bonferroni": "random alerter at the same rate matches the pre-onset warnings with p < 0.05 / number of arms",
    "beats_existing_alarm_pre_onset": "pre-onset warnings > existing low-pressure alarm pre-onset warnings on the same events",
}

CYCLE_BASES = ("decay_floor", "decay_median", "rise_median", "loaded_minutes_median", "idle_minutes_median",
               "cycles", "current_loaded", "oil_rise_loaded")
UNIT_FEATURES = ("duty_30m", "duty_60m", "loaded_gain_rate_60m", "idle_drop_rate_60m", "loaded_run_minutes",
                 "oil_temperature_mean_30m", "motor_current_mean_30m", "lps_fraction_30m", "tp3_mean_30m")
SUPERVISED = ("gbm_precursor", "gbm_onset", "gbm_replay")


def cycle_columns() -> list[str]:
    return [f"{base}_{hours}h" for base in CYCLE_BASES for hours in HOURS]


def load_unit(unit: str) -> pd.DataFrame:
    base = pd.read_parquet(UNITS_DIR / f"{unit}.parquet", columns=["timestamp", *UNIT_FEATURES])
    cycles = pd.read_parquet(CYCLES_DIR / f"{unit}_cycle5m.parquet")
    frame = base.merge(cycles, on="timestamp", how="left").sort_values("timestamp").reset_index(drop=True)
    return frame


def robust_z(frame: pd.DataFrame, fit: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    for column in columns:
        values = fit[column].dropna()
        centre = float(values.median()) if len(values) else 0.0
        spread = float(values.quantile(0.75) - values.quantile(0.25)) / 1.349 if len(values) else 1.0
        spread = max(spread, 1e-6 + 1e-3 * abs(centre))
        out[column] = ((frame[column] - centre) / spread).clip(-20, 20)
    return out


def label_free_scores(z: pd.DataFrame, stale: np.ndarray) -> dict[str, np.ndarray]:
    scores: dict[str, pd.Series] = {}
    for h in HOURS:
        leak = (z[f"decay_floor_{h}h"] - z[f"rise_median_{h}h"] + z[f"loaded_minutes_median_{h}h"]) / 3
        scores[f"decay_floor_{h}h"] = z[f"decay_floor_{h}h"]
        scores[f"rise_drop_{h}h"] = -z[f"rise_median_{h}h"]
        scores[f"loaded_long_{h}h"] = z[f"loaded_minutes_median_{h}h"]
        scores[f"cycle_rate_{h}h"] = z[f"cycles_{h}h"]
        scores[f"oil_current_{h}h"] = np.maximum(z[f"oil_rise_loaded_{h}h"], z[f"current_loaded_{h}h"])
        scores[f"leak_index_{h}h"] = leak
    daily = scores["leak_index_24h"].ffill()
    for days in (1, 3):
        scores[f"drift_ewma_{days}d"] = daily.ewm(span=days * 288, min_periods=72).mean()
    scores["cusum_3d"] = (scores["leak_index_6h"].clip(lower=1) - 1).fillna(0).rolling(3 * 288, min_periods=72).sum() / 288
    return {name: np.where(stale, 0.0, np.nan_to_num(series.to_numpy(dtype=float), nan=0.0)) for name, series in scores.items()}


def sustained(scores: np.ndarray, threshold: float, persistence: int) -> np.ndarray:
    above = pd.Series(scores >= threshold)
    return above.rolling(persistence, min_periods=persistence).min().fillna(0).astype(bool).to_numpy()


def calibrate(timestamps: pd.Series, scores: np.ndarray, persistence: int) -> float:
    days = max((timestamps.max() - timestamps.min()).total_seconds() / 86400, 1)
    finite = scores[np.isfinite(scores)]
    for threshold in np.unique(np.quantile(finite, np.linspace(0.90, 0.99995, 300))):
        if len(merged_alerts(timestamps.reset_index(drop=True), sustained(scores, threshold, persistence))) / days <= BUDGET:
            return float(threshold)
    return float(np.nextafter(finite.max(), np.inf))


def score_pre(alerts: list[pd.Timestamp], events: list[Event], start: pd.Timestamp, end: pd.Timestamp) -> dict:
    pre = pd.Timedelta(hours=PRE_HOURS)
    related_before = pd.Timedelta(hours=RELATED_BEFORE_HOURS)
    need = pd.Timedelta(minutes=OFFICIAL_NEED_MINUTES)
    related: set[pd.Timestamp] = set()
    rows = []
    for event in events:
        before = [a for a in alerts if event.start - pre <= a < event.start]
        in_time = [a for a in alerts if event.start - need <= a <= event.end - need]
        related.update(a for a in alerts if event.start - related_before <= a <= event.end)
        rows.append({
            "event_id": event.event_id,
            "kind": event.kind,
            "start": str(event.start),
            "warned_before_onset": bool(before),
            "lead_minutes": float((event.start - min(before)).total_seconds() / 60) if before else None,
            "caught_in_time_official": bool(in_time),
            "first_alert_minutes_after_start": float((min(in_time) - event.start).total_seconds() / 60) if in_time else None,
        })
    excluded = sum((min(e.end, end) - max(e.start - related_before, start)).total_seconds() / 86400
                   for e in events if e.end > start)
    healthy = max((end - start).total_seconds() / 86400 - excluded, 1)
    false_alerts = [a for a in alerts if a not in related]
    return {"events": rows, "merged_alerts": len(alerts), "false_alerts": len(false_alerts), "healthy_days": healthy,
            "test_days": (end - start).total_seconds() / 86400}


def pooled(results: list[dict]) -> dict:
    rows = [row for result in results for row in result["events"]]
    false_alerts = sum(r["false_alerts"] for r in results)
    healthy = sum(r["healthy_days"] for r in results)
    leads = [r["lead_minutes"] for r in rows if r["warned_before_onset"]]
    return {
        "events": len(rows),
        "warned_before_onset": sum(r["warned_before_onset"] for r in rows),
        "caught_in_time_official": sum(r["caught_in_time_official"] for r in rows),
        "false_alerts": false_alerts,
        "false_per_day": false_alerts / max(healthy, 1e-9),
        "median_lead_minutes": float(np.median(leads)) if leads else None,
    }


def random_p(results: list[dict]) -> tuple[float, float]:
    dist, expected, warned = np.array([1.0]), 0.0, 0
    for result in results:
        rate = result["merged_alerts"] / max(result["test_days"] * 1440, 1)
        for row in result["events"]:
            prob = 1 - np.exp(-rate * PRE_HOURS * 60)
            expected += prob
            dist = np.convolve(dist, [1 - prob, prob])
            warned += int(row["warned_before_onset"])
    return float(dist[warned:].sum()), expected


def rank(stats: dict) -> tuple:
    return (stats["false_per_day"] <= BUDGET, stats["warned_before_onset"], stats["caught_in_time_official"], -stats["false_per_day"])


class Unit:
    def __init__(self, name: str, events: list[Event]):
        self.name = name
        frame = load_unit(name)
        _, fit_end, cal_end = unit_splits(frame)
        self.frame = frame
        self.ts = frame["timestamp"]
        self.fit = (self.ts < fit_end).to_numpy()
        self.cal = ((self.ts >= fit_end) & (self.ts < cal_end)).to_numpy()
        self.test = (self.ts >= cal_end).to_numpy()
        self.columns = cycle_columns() + list(UNIT_FEATURES)
        self.z = robust_z(frame, frame[self.fit], self.columns)
        self.stale = frame["minutes_since_segment"].fillna(np.inf).to_numpy() > STALE_MINUTES
        self.test_ts = self.ts[self.test].reset_index(drop=True)
        self.cal_ts = self.ts[self.cal].reset_index(drop=True)
        self.start, self.end = self.test_ts.min(), self.test_ts.max()
        self.events = [e for e in events if e.end > self.start]
        self.all_events = events

    def evaluate(self, scores: np.ndarray, persistence: int) -> dict:
        threshold = calibrate(self.cal_ts, scores[self.cal], persistence)
        alerts = merged_alerts(self.test_ts, sustained(scores[self.test], threshold, persistence))
        result = score_pre(alerts, self.events, self.start, self.end)
        result["threshold"] = threshold
        return result

    def lps(self) -> dict:
        flags = self.frame.loc[self.test, "lps_fraction_30m"].fillna(0).to_numpy() > 0
        return score_pre(merged_alerts(self.test_ts, flags), self.events, self.start, self.end)

    def window_mask(self, event: Event, before_h: float, after_h: float) -> np.ndarray:
        return ((self.ts >= event.start - pd.Timedelta(hours=before_h)) & (self.ts < event.start + pd.Timedelta(hours=after_h))).to_numpy()

    def healthy_mask(self) -> np.ndarray:
        mask = ~self.stale
        for event in self.all_events:
            mask &= ~((self.ts >= event.start - pd.Timedelta(hours=48)) & (self.ts <= event.end + pd.Timedelta(hours=24))).to_numpy()
        return mask


def label_free_arm(units: dict[str, Unit]) -> dict:
    raw = {name: label_free_scores(unit.z, unit.stale) for name, unit in units.items()}
    configs = [(family, p) for family in next(iter(raw.values())) for p in PERSISTENCE]
    results = {name: {f"{f}|p{p}": units[name].evaluate(raw[name][f], p) for f, p in configs} for name in units}
    folds, held = [], []
    for name in units:
        others = [u for u in units if u != name]
        chosen = max(results[name], key=lambda c: rank(pooled([results[u][c] for u in others])))
        held.append(results[name][chosen])
        folds.append({"held_out": name, "chosen": chosen, "train_stats": pooled([results[u][chosen] for u in others]),
                      "held_out_stats": pooled([results[name][chosen]]), "events": results[name][chosen]["events"]})
    everywhere = max(results[next(iter(units))], key=lambda c: rank(pooled([results[u][c] for u in units])))
    board = sorted(({"config": c, **pooled([results[u][c] for u in units])} for c in results[next(iter(units))]),
                   key=lambda r: (-(r["false_per_day"] <= BUDGET), -r["warned_before_onset"], r["false_per_day"]))[:15]
    return {"folds": folds, "held": held, "best_all_units": everywhere, "leaderboard_all_units": board}


def supervised_arm(units: dict[str, Unit], kind: str) -> dict:
    rng = np.random.default_rng(SEED)
    columns = units[next(iter(units))].columns
    folds, held = [], []
    for name, target in units.items():
        xs, ys, origins = [], [], []
        onset_vectors = []
        for other, unit in units.items():
            if other == name:
                continue
            healthy = np.flatnonzero(unit.healthy_mask())
            negatives = rng.choice(healthy, size=min(len(healthy), 25_000), replace=False)
            xs.append(unit.z.iloc[negatives][columns].to_numpy())
            ys.append(np.zeros(len(negatives)))
            origins += ["OBSERVED"] * len(negatives)
            for event in unit.all_events:
                if kind == "gbm_onset":
                    mask = unit.window_mask(event, 0, 2) & ~unit.stale
                else:
                    mask = unit.window_mask(event, PRE_HOURS, 0) & ~unit.stale
                xs.append(unit.z[mask][columns].to_numpy())
                ys.append(np.ones(int(mask.sum())))
                origins += ["OBSERVED"] * int(mask.sum())
                onset = unit.window_mask(event, 0, 2) & ~unit.stale
                if onset.any():
                    onset_vectors.append(np.nan_to_num(unit.z[onset][columns].to_numpy()).mean(axis=0))
            if kind == "gbm_replay" and onset_vectors:
                base = rng.choice(healthy, size=3000, replace=True)
                signature = np.array(onset_vectors)[rng.integers(0, len(onset_vectors), size=3000)]
                alpha = rng.choice((0.15, 0.3, 0.5), size=(3000, 1))
                xs.append(np.nan_to_num(unit.z.iloc[base][columns].to_numpy()) + alpha * signature)
                ys.append(np.ones(3000))
                origins += ["SYNTHETIC_TRAINING_ONLY"] * 3000
        x, y = np.vstack(xs), np.concatenate(ys)
        model = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.05, max_leaf_nodes=31,
                                               l2_regularization=1.0, class_weight="balanced", random_state=SEED)
        model.fit(x, y)
        scores = model.predict_proba(target.z[columns].to_numpy())[:, 1]
        scores = np.where(target.stale, 0.0, scores)
        result = target.evaluate(scores, SUPERVISED_PERSISTENCE)
        held.append(result)
        folds.append({"held_out": name, "positives": int(y.sum()), "synthetic_rows": origins.count("SYNTHETIC_TRAINING_ONLY"),
                      "held_out_stats": pooled([result]), "events": result["events"]})
    return {"folds": folds, "held": held}


def growth_profiles(units: dict[str, Unit]) -> list[dict]:
    """Leak-down floor and leak index, as healthy-z, from 72 h before to 6 h after each reported start."""
    offsets = (-72, -48, -24, -12, -6, -3, -1, 0, 1, 3, 6)
    rows = []
    for unit in units.values():
        leak = (unit.z["decay_floor_1h"] - unit.z["rise_median_1h"] + unit.z["loaded_minutes_median_1h"]) / 3
        for event in unit.all_events:
            row = {"unit": unit.name, "event_id": event.event_id, "kind": event.kind}
            for hours in offsets:
                at = event.start + pd.Timedelta(hours=hours)
                index = int(np.searchsorted(unit.ts.to_numpy(), np.datetime64(at)))
                index = min(max(index, 0), len(unit.ts) - 1)
                row[f"leak_index_z_{hours:+d}h"] = None if unit.stale[index] else round(float(leak.iloc[index]), 2)
                row[f"decay_floor_z_{hours:+d}h"] = None if unit.stale[index] else round(float(unit.z["decay_floor_1h"].iloc[index]), 2)
            rows.append(row)
    return rows


def precursor_percentiles(units: dict[str, Unit]) -> list[dict]:
    """Leak index before each onset, as a percentile of the same unit's healthy test bins."""
    offsets = (-48, -24, -12, -6, -3, -1, 0, 1)
    rows = []
    for unit in units.values():
        leak = (unit.z["decay_floor_1h"] - unit.z["rise_median_1h"] + unit.z["loaded_minutes_median_1h"]) / 3
        leak = leak.where(~pd.Series(unit.stale))
        healthy = leak[unit.healthy_mask() & unit.test].dropna().to_numpy()
        for event in unit.all_events:
            row = {"unit": unit.name, "event_id": event.event_id, "kind": event.kind}
            for hours in offsets:
                at = event.start + pd.Timedelta(hours=hours)
                window = leak[(unit.ts >= at - pd.Timedelta(minutes=30)) & (unit.ts <= at)].dropna()
                row[f"pctl_{hours:+d}h"] = None if window.empty else round(float((healthy < window.median()).mean() * 100), 1)
            rows.append(row)
    return rows


def exploratory_rolling_baseline(units: dict[str, Unit]) -> dict:
    """POST-HOC: leak index relative to its own trailing 7-day median, lagged one day.

    Designed after seeing that MetroPT-3 drifts above its February baseline. Reported
    for transparency only; it is not eligible for promotion.
    """
    results = []
    for unit in units.values():
        leak = (unit.z["decay_floor_1h"] - unit.z["rise_median_1h"] + unit.z["loaded_minutes_median_1h"]) / 3
        relative = leak - leak.rolling(7 * 288, min_periods=288).median().shift(288)
        scores = np.where(unit.stale, 0.0, np.nan_to_num(relative.to_numpy(dtype=float), nan=0.0))
        results.append(unit.evaluate(scores, INJECTION_PERSISTENCE))
    p, expected = random_p(results)
    return {"status": "EXPLORATORY_POST_HOC_NOT_PROMOTABLE", "pooled": pooled(results),
            "random_alerter": {"expected": expected, "p": p},
            "events": [row for result in results for row in result["events"]]}


INJECTION_FAMILY = "leak_index_1h"
INJECTION_PERSISTENCE = 3


def injection_study(units: dict[str, Unit], family: str, persistence: int) -> dict:
    """Inject a leak ramping from 0 to delta over 24 h into real healthy cycles; time to first alert."""
    rng = np.random.default_rng(SEED)
    unit = units["METROPT3_UCI_791"]
    segments = pd.read_parquet(CYCLES_DIR / f"{unit.name}_segments.parquet")
    idle_decay = float((-segments.loc[segments["idle"] == 1, "rate"]).median())
    baseline_scores = label_free_scores(unit.z, unit.stale)[family]
    threshold = calibrate(unit.cal_ts, baseline_scores[unit.cal], persistence)
    healthy = unit.healthy_mask() & unit.test
    candidates = unit.ts[healthy].reset_index(drop=True)
    starts = [candidates.iloc[i] for i in rng.choice(len(candidates) - 600, size=30, replace=False)]
    curve = []
    for fraction in (0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0):
        delta_max = fraction * idle_decay
        detected, hours_to_alert = 0, []
        for start in starts:
            lo, hi = start - pd.Timedelta(hours=30), start + pd.Timedelta(hours=30)
            local = segments[(segments["end"] >= lo) & (segments["end"] <= hi)].reset_index(drop=True)
            elapsed = (local["end"] - start).dt.total_seconds().to_numpy() / 3600
            delta = delta_max * np.clip(elapsed / 24, 0, 1)
            injected = inject_leak(local, delta)
            injected["end"] = local["end"]
            grid = pd.DatetimeIndex(unit.ts[(unit.ts >= start) & (unit.ts <= start + pd.Timedelta(hours=24))])
            feats = bin_features(injected, grid)
            local_z = robust_z(feats, unit.frame[unit.fit], [c for c in cycle_columns()])
            for column in UNIT_FEATURES:
                local_z[column] = 0.0
            stale = feats["minutes_since_segment"].fillna(np.inf).to_numpy() > STALE_MINUTES
            scores = label_free_scores(local_z, stale)[family]
            flags = sustained(scores, threshold, persistence)
            if flags.any():
                detected += 1
                hours_to_alert.append(float((grid[int(np.argmax(flags))] - start).total_seconds() / 3600))
        curve.append({"leak_fraction_of_normal_idle_decay": fraction, "delta_bar_per_min_at_24h": round(delta_max, 5),
                      "detected_within_24h": detected, "trials": len(starts),
                      "median_hours_to_alert": float(np.median(hours_to_alert)) if hours_to_alert else None})
    return {"unit": unit.name, "family": family, "persistence": persistence, "threshold": threshold,
            "control": "leak_fraction 0.0 is the same windows with no injection; detections there are baseline false alerts",
            "normal_idle_decay_bar_per_min": idle_decay,
            "ramp_hours": 24, "origin": "SYNTHETIC_TRAINING_ONLY injection into OBSERVED healthy cycles", "curve": curve}


def main() -> int:
    events = unit_events()
    units = {name: Unit(name, unit_events_) for name, unit_events_ in events.items()}
    print("units loaded", {n: len(u.events) for n, u in units.items()}, flush=True)
    lps = pooled([u.lps() for u in units.values()])
    arms: dict[str, dict] = {"label_free_cycle_physics": label_free_arm(units)}
    print("label-free done", pooled(arms["label_free_cycle_physics"]["held"]), flush=True)
    for kind in SUPERVISED:
        arms[kind] = supervised_arm(units, kind)
        print(kind, "done", pooled(arms[kind]["held"]), flush=True)
    n_arms = len(arms)
    summary = {}
    for name, arm in arms.items():
        stats = pooled(arm["held"])
        p, expected = random_p(arm["held"])
        gates = {
            "pre_onset_three_of_nine": stats["warned_before_onset"] >= 3,
            "false_alert_budget": stats["false_per_day"] <= BUDGET,
            "beats_random_bonferroni": p < 0.05 / n_arms,
            "beats_existing_alarm_pre_onset": stats["warned_before_onset"] > lps["warned_before_onset"],
        }
        summary[name] = {"held_out": stats, "random_alerter": {"expected": expected, "p": p}, "gates": gates,
                         "status": "PROMOTED" if all(gates.values()) else "NO_PROMOTION"}
    report = {
        "study": "PNEUMORA precursor study: warn before reported onset, held out by compressor",
        "declared_gates": GATES,
        "pre_onset_window_hours": PRE_HOURS,
        "related_before_hours": RELATED_BEFORE_HOURS,
        "existing_alarm_same_events": lps,
        "arms": {name: {k: v for k, v in arm.items() if k != "held"} for name, arm in arms.items()},
        "summary": summary,
        "any_promoted": any(s["status"] == "PROMOTED" for s in summary.values()),
        "growth_profiles": growth_profiles(units),
        "precursor_percentiles": precursor_percentiles(units),
        "exploratory_rolling_baseline": exploratory_rolling_baseline(units),
        "injection_sensitivity": injection_study(units, INJECTION_FAMILY, INJECTION_PERSISTENCE),
        "caveat": ("Nine failures cannot estimate future precision. The physics families and the replay idea were chosen "
                   "after earlier studies inspected these failures, so a pass would be cross-validation, not an untouched test."),
    }
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"existing_alarm": lps, "summary": summary}, indent=2, default=str))
    print(json.dumps(report["injection_sensitivity"]["curve"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
