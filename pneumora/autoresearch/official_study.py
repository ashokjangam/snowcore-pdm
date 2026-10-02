"""Official-protocol detection study: develop on MetroPT-3, freeze, test once externally.

Target (Veloso et al., Scientific Data 2022): the operator needs a failure detected at
least two hours before the train becomes non-operational. A failure is "caught in time"
when a merged alert lands in [reported start - 120 min, reported end - 120 min].
Alerts in [start - 120 min, end] are related; every other alert is false.

The recipe is unit-agnostic: learn normal behaviour from the first 21 days of a unit,
calibrate the alert threshold on the next 14 days against the false-alert budget, then
score the remainder. No failure label is used to fit or calibrate.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPRegressor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "autoresearch"))

from pneumora.contracts import ALERT_MERGE_MINUTES, FAILURES, MAX_FALSE_ALERTS_PER_HEALTHY_DAYS  # noqa: E402
from leak_physics import fit_baseline, leak_score, physics_features  # noqa: E402
from run_campaign import MODEL_FEATURES  # noqa: E402

FEATURES_PATH = ROOT / "data" / "processed" / "features_5m.parquet"
OUTPUT = ROOT / "autoresearch" / "official_study.json"
FREEZE = ROOT / "autoresearch" / "official_freeze.json"

FIT_DAYS = 21
CALIBRATION_DAYS = 14
REMOVAL_NEED_MINUTES = 120
FAMILIES = ("pca_residual", "autoencoder", "isolation_forest", "corroboration_k2", "corroboration_k3")
PHYSICS_FAMILIES = ("leak_w30", "leak_w60", "leakdecay_w30", "leakdecay_w60", "loaded_run")
TELEMETRY_PATH = ROOT / "data" / "processed" / "telemetry.parquet"
MODES = ("static", "adaptive")
SMOOTHING_BINS = (1, 6, 12, 24)
PERSISTENCE_BINS = (1, 3, 6, 12)


@dataclass(frozen=True)
class Event:
    event_id: str
    start: pd.Timestamp
    end: pd.Timestamp
    kind: str


def metropt3_events() -> list[Event]:
    return [Event(f.episode_id, pd.Timestamp(f.start), pd.Timestamp(f.end), "air_leak") for f in FAILURES]


def unit_splits(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    first = frame["timestamp"].min().normalize()
    fit_end = first + pd.Timedelta(days=FIT_DAYS)
    cal_end = fit_end + pd.Timedelta(days=CALIBRATION_DAYS)
    return frame[frame["timestamp"] < fit_end], fit_end, cal_end


Z_CLIP = 10.0
REFIT_EVERY_DAYS = 7


def merged_alerts(timestamps: pd.Series, flags: np.ndarray) -> list[pd.Timestamp]:
    """One alert per episode; an episode ends once flags stop for more than the merge gap."""
    raised = list(pd.to_datetime(timestamps[np.asarray(flags, dtype=bool)]))
    if not raised:
        return []
    gap = pd.Timedelta(minutes=ALERT_MERGE_MINUTES)
    episodes = [raised[0]]
    for previous, current in zip(raised, raised[1:]):
        if current - previous > gap:
            episodes.append(current)
    return episodes


def merged_alerts(timestamps: pd.Series, flags: np.ndarray) -> list[pd.Timestamp]:
    """One alert per episode; an episode ends once flags stop for more than the merge gap."""
    raised = list(pd.to_datetime(timestamps[np.asarray(flags, dtype=bool)]))
    if not raised:
        return []
    gap = pd.Timedelta(minutes=ALERT_MERGE_MINUTES)
    episodes = [raised[0]]
    for previous, current in zip(raised, raised[1:]):
        if current - previous > gap:
            episodes.append(current)
    return episodes


def standardise(imputer, centre: np.ndarray, scale: np.ndarray, frame: pd.DataFrame) -> np.ndarray:
    return np.clip((imputer.transform(frame[MODEL_FEATURES]) - centre) / scale, -Z_CLIP, Z_CLIP)


def physics_spec(family: str) -> tuple[int, bool]:
    if family == "loaded_run":
        return 0, False
    kind, window = family.split("_w")
    return int(window), kind == "leakdecay"


def fit_family(family: str, train: pd.DataFrame):
    if family == "loaded_run":
        return {"family": family}
    if family in PHYSICS_FAMILIES:
        minutes, _ = physics_spec(family)
        return {"family": family, "baseline": fit_baseline(train, minutes)}
    imputer = SimpleImputer(strategy="median").fit(train[MODEL_FEATURES])
    values = imputer.transform(train[MODEL_FEATURES])
    centre = values.mean(axis=0)
    scale = np.maximum(values.std(axis=0), 1e-3 * np.abs(centre) + 1e-6)
    z = np.clip((values - centre) / scale, -Z_CLIP, Z_CLIP)
    if family == "pca_residual":
        model = PCA(n_components=0.95).fit(z)
    elif family == "autoencoder":
        model = MLPRegressor(hidden_layer_sizes=(12, 4, 12), max_iter=120, random_state=42, early_stopping=True)
        model.fit(z, z)
    elif family == "isolation_forest":
        model = IsolationForest(n_estimators=200, random_state=42, n_jobs=-1).fit(z)
    else:
        model = None
    bundle = {"family": family, "imputer": imputer, "centre": centre, "scale": scale, "model": model, "norm": 1.0}
    bundle["norm"] = max(float(np.quantile(_score_z(bundle, z), 0.99)), 1e-9)
    return bundle


def _score_z(bundle: dict, z: np.ndarray) -> np.ndarray:
    family, model = bundle["family"], bundle["model"]
    if family == "pca_residual":
        return np.mean((z - model.inverse_transform(model.transform(z))) ** 2, axis=1)
    if family == "autoencoder":
        return np.mean((z - model.predict(z)) ** 2, axis=1)
    if family == "isolation_forest":
        return -model.decision_function(z) + 0.5
    k = int(family[-1])
    return -np.sort(-np.abs(z), axis=1)[:, k - 1]


def raw_score(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    if bundle["family"] == "loaded_run":
        return frame["loaded_run_minutes"].fillna(0).to_numpy()
    if bundle["family"] in PHYSICS_FAMILIES:
        minutes, use_decay = physics_spec(bundle["family"])
        return leak_score(frame, bundle["baseline"], minutes, use_decay)
    z = standardise(bundle["imputer"], bundle["centre"], bundle["scale"], frame)
    return _score_z(bundle, z) / bundle["norm"]


def adaptive_score(family: str, frame: pd.DataFrame, fit_end: pd.Timestamp) -> np.ndarray:
    """Refit weekly on the trailing FIT_DAYS of bins the previous model found ordinary."""
    timestamps = frame["timestamp"]
    scores = np.full(len(frame), np.nan)
    bundle = fit_family(family, frame[timestamps < fit_end])
    cursor = timestamps.min()
    refit_at = fit_end
    while cursor <= timestamps.max():
        block = (timestamps >= cursor) & (timestamps < refit_at)
        if block.any():
            scores[block.to_numpy()] = raw_score(bundle, frame[block])
        cursor = refit_at
        window = (timestamps >= refit_at - pd.Timedelta(days=FIT_DAYS)) & (timestamps < refit_at)
        ordinary = window.to_numpy() & (scores < 1.0)
        if ordinary.sum() > 500:
            bundle = fit_family(family, frame[ordinary])
        refit_at = refit_at + pd.Timedelta(days=REFIT_EVERY_DAYS)
    return scores


def smooth(scores: np.ndarray, bins: int) -> np.ndarray:
    if bins <= 1:
        return scores
    return pd.Series(scores).rolling(bins, min_periods=1).median().to_numpy()


def alert_times(timestamps: pd.Series, scores: np.ndarray, threshold: float, persistence: int) -> list[pd.Timestamp]:
    above = pd.Series(scores >= threshold)
    sustained = above.rolling(persistence, min_periods=persistence).min().fillna(0).astype(bool).to_numpy()
    return merged_alerts(timestamps.reset_index(drop=True), sustained)


def calibrate(timestamps: pd.Series, scores: np.ndarray, persistence: int) -> float:
    days = max((timestamps.max() - timestamps.min()).total_seconds() / 86400, 1)
    finite = scores[np.isfinite(scores)]
    for threshold in np.unique(np.quantile(finite, np.linspace(0.90, 0.99995, 300))):
        if len(alert_times(timestamps, scores, threshold, persistence)) / days <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS:
            return float(threshold)
    return float(np.nextafter(finite.max(), np.inf))


def score_events(alerts: list[pd.Timestamp], events: list[Event], start: pd.Timestamp, end: pd.Timestamp) -> dict:
    need = pd.Timedelta(minutes=REMOVAL_NEED_MINUTES)
    related: set[pd.Timestamp] = set()
    rows = []
    for event in events:
        in_time = [a for a in alerts if event.start - need <= a <= event.end - need]
        related.update(a for a in alerts if event.start - need <= a <= event.end)
        first = min(in_time) if in_time else None
        rows.append(
            {
                "event_id": event.event_id,
                "kind": event.kind,
                "start": str(event.start),
                "end": str(event.end),
                "caught_in_time": bool(in_time),
                "first_alert": str(first) if first is not None else None,
                "minutes_before_end": float((event.end - first).total_seconds() / 60) if first is not None else None,
                "minutes_after_start": float((first - event.start).total_seconds() / 60) if first is not None else None,
            }
        )
    failure_days = sum(
        (min(e.end, end) - max(e.start - need, start)).total_seconds() / 86400 for e in events if e.end > start
    )
    healthy_days = max((end - start).total_seconds() / 86400 - failure_days, 1)
    false_alerts = [a for a in alerts if a not in related]
    caught = sum(r["caught_in_time"] for r in rows)
    leads = [r["minutes_before_end"] for r in rows if r["caught_in_time"]]
    return {
        "events": rows,
        "caught_in_time": caught,
        "n_events": len(rows),
        "merged_alerts": len(alerts),
        "false_alerts": len(false_alerts),
        "healthy_days": healthy_days,
        "false_alerts_per_healthy_day": len(false_alerts) / healthy_days,
        "median_minutes_before_end": float(np.median(leads)) if leads else None,
    }


def random_alerter_null(result: dict, test_days: float) -> dict:
    """Chance of matching the catches with alerts placed at random at the same overall rate."""
    rate_per_minute = result["merged_alerts"] / max(test_days * 1440, 1)
    probs = []
    for row in result["events"]:
        window = (pd.Timestamp(row["end"]) - pd.Timestamp(row["start"])).total_seconds() / 60
        probs.append(1 - np.exp(-rate_per_minute * max(window, 0)))
    dist = np.array([1.0])
    for p in probs:
        dist = np.convolve(dist, [1 - p, p])
    caught = result["caught_in_time"]
    return {"expected_catches": float(sum(probs)), "p_at_least_observed": float(dist[caught:].sum())}


def lps_alerts(frame: pd.DataFrame) -> list[pd.Timestamp]:
    return merged_alerts(frame["timestamp"].reset_index(drop=True), frame["lps_fraction_30m"].fillna(0).to_numpy() > 0)


def run_unit(frame: pd.DataFrame, events: list[Event], configs: list[tuple[str, int, int]]) -> dict:
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    train, fit_end, cal_end = unit_splits(frame)
    cal_mask = (frame["timestamp"] >= fit_end) & (frame["timestamp"] < cal_end)
    test_mask = frame["timestamp"] >= cal_end
    test_ts = frame.loc[test_mask, "timestamp"].reset_index(drop=True)
    start, end = test_ts.min(), test_ts.max()
    scored = [e for e in events if e.end > start]
    raw = {}
    for family, mode in {(c[0], c[1]) for c in configs}:
        if mode == "static":
            raw[(family, mode)] = raw_score(fit_family(family, train), frame)
        else:
            raw[(family, mode)] = adaptive_score(family, frame, fit_end)
    results = {}
    for family, mode, bins, persistence in configs:
        series = smooth(raw[(family, mode)], bins)
        threshold = calibrate(frame.loc[cal_mask, "timestamp"].reset_index(drop=True), series[cal_mask.to_numpy()], persistence)
        alerts = alert_times(test_ts, series[test_mask.to_numpy()], threshold, persistence)
        result = score_events(alerts, scored, start, end)
        result["threshold"] = threshold
        results[config_name(family, mode, bins, persistence)] = result
    lps = score_events(lps_alerts(frame[test_mask]), scored, start, end)
    return {
        "fit_window": [str(frame["timestamp"].min()), str(fit_end)],
        "calibration_window": [str(fit_end), str(cal_end)],
        "test_window": [str(start), str(end)],
        "events_scored": [e.event_id for e in scored],
        "configs": results,
        "lps_existing_alarm": lps,
    }


def rank_key(result: dict, event_ids: set[str]) -> tuple:
    caught = sum(r["caught_in_time"] for r in result["events"] if r["event_id"] in event_ids)
    leads = [r["minutes_before_end"] for r in result["events"] if r["event_id"] in event_ids and r["caught_in_time"]]
    within_budget = result["false_alerts_per_healthy_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS
    return (within_budget, caught, -result["false_alerts_per_healthy_day"], float(np.median(leads)) if leads else -1e9)


def config_name(family: str, mode: str, bins: int, persistence: int) -> str:
    return f"{family}|{mode}|s{bins}|p{persistence}"


def parse_config(name: str) -> tuple[str, str, int, int]:
    family, mode, bins, persistence = name.split("|")
    return family, mode, int(bins[1:]), int(persistence[1:])


def all_configs() -> list[tuple[str, str, int, int]]:
    learned = [(f, m, s, p) for f in FAMILIES for m in MODES for s in SMOOTHING_BINS for p in PERSISTENCE_BINS]
    physics = [(f, "static", s, p) for f in PHYSICS_FAMILIES for s in SMOOTHING_BINS for p in PERSISTENCE_BINS]
    return learned + physics


def load_unit_frame(features_path: Path, telemetry_path: Path) -> pd.DataFrame:
    features = pd.read_parquet(features_path)
    telemetry = pd.read_parquet(telemetry_path, columns=["timestamp", "tp3", "comp"])
    return features.merge(physics_features(telemetry), on="timestamp", how="left")


def main() -> int:
    frame = load_unit_frame(FEATURES_PATH, TELEMETRY_PATH)
    events = metropt3_events()
    unit = run_unit(frame, events, all_configs())
    configs = unit["configs"]
    ids = {e.event_id for e in events}
    folds = []
    for held in sorted(ids):
        chosen = max(configs, key=lambda name: rank_key(configs[name], ids - {held}))
        held_row = next(r for r in configs[chosen]["events"] if r["event_id"] == held)
        folds.append({"held_out": held, "chosen": chosen, "held_out_caught_in_time": held_row["caught_in_time"],
                      "held_out_minutes_before_end": held_row["minutes_before_end"]})
    final = max(configs, key=lambda name: rank_key(configs[name], ids))
    lps = unit["lps_existing_alarm"]
    lofo_caught = sum(f["held_out_caught_in_time"] for f in folds)
    test_days = (pd.Timestamp(unit["test_window"][1]) - pd.Timestamp(unit["test_window"][0])).total_seconds() / 86400
    null = random_alerter_null(configs[final], test_days)
    gates = {
        "beats_random_alerter_p05": null["p_at_least_observed"] < 0.05,
        "lofo_three_of_four": lofo_caught >= 3,
        "test_false_alert_budget": configs[final]["false_alerts_per_healthy_day"] <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS,
        "beats_existing_lps_alarm": (configs[final]["caught_in_time"], configs[final]["median_minutes_before_end"] or 0)
        > (lps["caught_in_time"], (lps["median_minutes_before_end"] or 0) + 30),
    }
    report = {
        "study": "PNEUMORA official-protocol detection, MetroPT-3 development",
        "target": "merged alert in [reported start - 120 min, reported end - 120 min]",
        "protocol_source": "Veloso et al. 2022, Scientific Data 9:764, evaluation protocol",
        "recipe": {"fit_days": FIT_DAYS, "calibration_days": CALIBRATION_DAYS, "merge_minutes": ALERT_MERGE_MINUTES,
                   "false_alert_budget_per_day": MAX_FALSE_ALERTS_PER_HEALTHY_DAYS, "features": MODEL_FEATURES},
        "role_of_metropt3": "DEVELOPMENT (all four episodes have been seen by earlier studies)",
        "unit": {k: v for k, v in unit.items() if k != "configs"},
        "leave_one_failure_out": {"folds": folds, "held_out_caught_in_time": lofo_caught},
        "final_config": final,
        "final_result": configs[final],
        "random_alerter_null": null,
        "development_gates": gates,
        "development_pass": all(gates.values()),
        "top_configs": sorted(
            ({"config": n, **{k: configs[n][k] for k in ("caught_in_time", "false_alerts_per_healthy_day", "median_minutes_before_end")}}
             for n in configs),
            key=lambda row: (-row["caught_in_time"], row["false_alerts_per_healthy_day"]),
        )[:15],
    }
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("leave_one_failure_out", "final_config", "random_alerter_null", "development_gates", "top_configs")}, indent=2, default=str))
    print(json.dumps([{k: r[k] for k in ("event_id", "caught_in_time", "minutes_after_start", "minutes_before_end")} for r in configs[final]["events"]], default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
