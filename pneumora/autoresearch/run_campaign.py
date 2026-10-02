"""Frozen chronological MetroPT-3 predictive-maintenance campaign."""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "autoresearch"))

from pneumora.contracts import (  # noqa: E402
    ALERT_MERGE_MINUTES,
    CALIBRATION_END,
    FAILURES,
    FIT_END,
    MAX_FALSE_ALERTS_PER_HEALTHY_DAYS,
    PRIMARY_HORIZON_MINUTES,
)
from simulator import fit_parameters, generate_leaks, realism_report  # noqa: E402

FEATURES_PATH = ROOT / "data" / "processed" / "features_5m.parquet"
OUTPUT = ROOT / "autoresearch" / "campaign.json"
CHAMPION = ROOT / "autoresearch" / "champion.json"
MODEL = ROOT / "autoresearch" / "champion.joblib"
PREDICTIONS = ROOT / "data" / "product" / "predictions.parquet"

MODEL_FEATURES = [
    "loaded_fraction_2h",
    "cycle_starts_2h",
    "tp3_reservoir_gap",
    "tp2_slope_30m",
    "tp2_slope_120m",
    "tp3_slope_30m",
    "tp3_slope_120m",
    "reservoirs_slope_30m",
    "reservoirs_slope_120m",
    "dv_pressure_mean_30m",
    "dv_pressure_mean_120m",
    "motor_current_mean_30m",
    "motor_current_mean_120m",
    "motor_current_std_120m",
    "oil_temperature_mean_30m",
    "oil_temperature_mean_120m",
    "oil_temperature_std_120m",
    "h1_mean_120m",
]


def merged_alerts(timestamps: pd.Series, flags: np.ndarray) -> list[pd.Timestamp]:
    raised = list(pd.to_datetime(timestamps[np.asarray(flags, dtype=bool)]))
    if not raised:
        return []
    episodes = [raised[0]]
    for timestamp in raised[1:]:
        if timestamp - episodes[-1] > pd.Timedelta(minutes=ALERT_MERGE_MINUTES):
            episodes.append(timestamp)
    return episodes


def calibrate_threshold(timestamps: pd.Series, scores: np.ndarray) -> tuple[float, dict]:
    timestamps = pd.to_datetime(timestamps).reset_index(drop=True)
    scores = np.asarray(scores, dtype=float)
    days = max((timestamps.max() - timestamps.min()).total_seconds() / 86400, 1)
    candidates = np.unique(np.quantile(scores[np.isfinite(scores)], np.linspace(0.90, 0.9999, 250)))
    chosen = float(np.nextafter(candidates[-1], np.inf))
    chosen_alerts: list[pd.Timestamp] = []
    for threshold in candidates:
        alerts = merged_alerts(timestamps, scores >= threshold)
        if len(alerts) / days <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS:
            chosen, chosen_alerts = float(threshold), alerts
            break
    return chosen, {
        "healthy_days": days,
        "merged_alerts": len(chosen_alerts),
        "false_alerts_per_healthy_day": len(chosen_alerts) / days,
        "budget": MAX_FALSE_ALERTS_PER_HEALTHY_DAYS,
    }


def evaluate(timestamps: pd.Series, scores: np.ndarray, threshold: float) -> tuple[dict, pd.DataFrame]:
    alerts = merged_alerts(timestamps, scores >= threshold)
    rows = []
    hit_alerts: set[pd.Timestamp] = set()
    for failure in FAILURES:
        start = pd.Timestamp(failure.start)
        window_start = start - pd.Timedelta(minutes=PRIMARY_HORIZON_MINUTES)
        candidates = [alert for alert in alerts if window_start <= alert <= start]
        alert = min(candidates) if candidates else pd.NaT
        if candidates:
            hit_alerts.update(candidates)
        rows.append(
            {
                "episode_id": failure.episode_id,
                "failure_start": start,
                "alert_at": alert,
                "hit_2h": bool(candidates),
                "lead_minutes": float((start - alert).total_seconds() / 60) if candidates else None,
                "onset_precision": failure.onset_precision,
            }
        )
    episode_frame = pd.DataFrame(rows)
    false_alerts = [alert for alert in alerts if alert not in hit_alerts]
    test_days = max((pd.to_datetime(timestamps).max() - pd.to_datetime(timestamps).min()).total_seconds() / 86400, 1)
    return {
        "observed_episodes": len(rows),
        "episodes_warned_2h": int(episode_frame["hit_2h"].sum()),
        "episode_recall_2h": float(episode_frame["hit_2h"].mean()),
        "merged_alerts": len(alerts),
        "alert_precision": len(hit_alerts) / len(alerts) if alerts else 0.0,
        "false_alerts": len(false_alerts),
        "false_alerts_per_day": len(false_alerts) / test_days,
        "median_lead_minutes": float(episode_frame["lead_minutes"].dropna().median())
        if episode_frame["hit_2h"].any()
        else None,
        "evaluation_origin": "OBSERVED_METROPT3",
    }, episode_frame


def baseline_scores(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    duty = (
        frame["loaded_fraction_2h"]
        + 0.15 * frame["cycle_starts_2h"].rank(pct=True)
        - 0.1 * frame["reservoirs_slope_120m"].clip(lower=0)
    ).to_numpy()
    cycle = (
        frame["cycle_starts_2h"].rank(pct=True)
        + frame["tp3_reservoir_gap"].rank(pct=True)
        - frame["reservoirs_slope_120m"].rank(pct=True)
    ).to_numpy()
    lps = frame["lps_fraction_30m"].fillna(0).to_numpy()
    return {"lps_existing_alarm": lps, "duty_cycle_rule": duty, "cycle_pressure_rule": cycle}


def fit_unsupervised(train: pd.DataFrame) -> dict[str, tuple[object, callable]]:
    x = train[MODEL_FEATURES]
    isolation = make_pipeline(
        SimpleImputer(strategy="median"),
        RobustScaler(),
        IsolationForest(n_estimators=200, contamination="auto", random_state=42, n_jobs=-1),
    )
    isolation.fit(x)
    pca = make_pipeline(SimpleImputer(strategy="median"), RobustScaler(), PCA(n_components=0.95))
    pca.fit(x)
    auto_imputer = SimpleImputer(strategy="median")
    auto_scaler = RobustScaler()
    auto_x = auto_scaler.fit_transform(auto_imputer.fit_transform(x))
    autoencoder = MLPRegressor(
        hidden_layer_sizes=(10, 4, 10),
        max_iter=80,
        random_state=42,
        early_stopping=True,
    )
    autoencoder.fit(auto_x, auto_x)
    auto_bundle = {"imputer": auto_imputer, "scaler": auto_scaler, "model": autoencoder}
    return {
        "isolation_forest": (isolation, lambda model, values: -model.decision_function(values)),
        "pca_residual": (
            pca,
            lambda model, values: np.mean(
                (model.named_steps["robustscaler"].transform(model.named_steps["simpleimputer"].transform(values))
                 - model.named_steps["pca"].inverse_transform(model.named_steps["pca"].transform(
                     model.named_steps["robustscaler"].transform(model.named_steps["simpleimputer"].transform(values))
                 ))) ** 2,
                axis=1,
            ),
        ),
        "compact_autoencoder": (
            auto_bundle,
            lambda bundle, values: (
                lambda transformed: np.mean(
                    (transformed - bundle["model"].predict(transformed)) ** 2,
                    axis=1,
                )
            )(bundle["scaler"].transform(bundle["imputer"].transform(values))),
        ),
    }


def fit_supervised(train: pd.DataFrame, synthetic: pd.DataFrame) -> object:
    observed = train.sample(min(len(train), 8000), random_state=42).copy()
    observed["target_failure_2h"] = 0
    combined = pd.concat([observed, synthetic], ignore_index=True)
    model = make_pipeline(
        SimpleImputer(strategy="median"),
        HistGradientBoostingClassifier(max_depth=5, max_iter=180, learning_rate=0.06, random_state=42),
    )
    model.fit(combined[MODEL_FEATURES], combined["target_failure_2h"])
    return model


def main() -> int:
    frame = pd.read_parquet(FEATURES_PATH).sort_values("timestamp")
    train = frame[frame["timestamp"] < pd.Timestamp(FIT_END)].copy()
    calibration = frame[
        (frame["timestamp"] >= pd.Timestamp(FIT_END))
        & (frame["timestamp"] < pd.Timestamp(CALIBRATION_END))
    ].copy()
    test = frame[frame["timestamp"] >= pd.Timestamp(CALIBRATION_END)].copy()
    if min(len(train), len(calibration), len(test)) == 0:
        raise ValueError("Chronological February/March/April-July splits are incomplete")

    parameters = fit_parameters(train)
    realism = realism_report(train, calibration, parameters)
    synthetic = generate_leaks(train, parameters, copies=2)
    wrong = generate_leaks(train, parameters, copies=2, wrong_physics=True)
    arms: dict[str, dict] = {}
    fitted: dict[str, object] = {}
    episode_tables: dict[str, list[dict]] = {}

    baseline_cal = baseline_scores(calibration)
    baseline_test = baseline_scores(test)
    for name in baseline_cal:
        threshold, cal_metrics = calibrate_threshold(calibration["timestamp"], baseline_cal[name])
        result, episodes = evaluate(test["timestamp"], baseline_test[name], threshold)
        arms[name] = {"threshold": threshold, "calibration": cal_metrics, "observed_test": result}
        episode_tables[name] = episodes.astype(object).where(pd.notna(episodes), None).to_dict("records")

    unsupervised = fit_unsupervised(train)
    for name, (model, scorer) in unsupervised.items():
        threshold, cal_metrics = calibrate_threshold(calibration["timestamp"], scorer(model, calibration[MODEL_FEATURES]))
        test_scores = scorer(model, test[MODEL_FEATURES])
        result, episodes = evaluate(test["timestamp"], test_scores, threshold)
        arms[name] = {"threshold": threshold, "calibration": cal_metrics, "observed_test": result}
        episode_tables[name] = episodes.astype(object).where(pd.notna(episodes), None).to_dict("records")
        fitted[name] = model

    for name, generated in (
        ("physics_synthetic_gbdt", synthetic),
        ("wrong_physics_control", wrong),
    ):
        model = fit_supervised(train, generated)
        cal_scores = model.predict_proba(calibration[MODEL_FEATURES])[:, 1]
        threshold, cal_metrics = calibrate_threshold(calibration["timestamp"], cal_scores)
        test_scores = model.predict_proba(test[MODEL_FEATURES])[:, 1]
        result, episodes = evaluate(test["timestamp"], test_scores, threshold)
        arms[name] = {"threshold": threshold, "calibration": cal_metrics, "observed_test": result}
        episode_tables[name] = episodes.astype(object).where(pd.notna(episodes), None).to_dict("records")
        fitted[name] = model

    duty_hits = arms["duty_cycle_rule"]["observed_test"]["episodes_warned_2h"]
    eligible = []
    for name, arm in arms.items():
        result = arm["observed_test"]
        passes = {
            "calibration_workload": arm["calibration"]["false_alerts_per_healthy_day"]
            <= MAX_FALSE_ALERTS_PER_HEALTHY_DAYS + 1e-12,
            "three_of_four": result["episodes_warned_2h"] >= 3,
            "beats_duty_baseline": result["episodes_warned_2h"] > duty_hits,
            "positive_lead": (result["median_lead_minutes"] or 0) > 0,
            "not_control": name != "wrong_physics_control",
        }
        arm["promotion_gates"] = passes
        if all(passes.values()):
            eligible.append(name)
    promoted = max(
        eligible,
        key=lambda name: (
            arms[name]["observed_test"]["episodes_warned_2h"],
            -arms[name]["observed_test"]["false_alerts_per_day"],
        ),
        default=None,
    )
    control_matches = (
        arms["wrong_physics_control"]["observed_test"]["episodes_warned_2h"]
        >= arms.get(promoted, {"observed_test": {"episodes_warned_2h": math.inf}})["observed_test"]["episodes_warned_2h"]
    )
    if control_matches:
        promoted = None

    report = {
        "study": "PNEUMORA MetroPT-3 frozen 2-hour failure forecast",
        "split": {"fit": "February", "calibration": "March", "observed_test": "April-July"},
        "target": "merged alert episode within 120 minutes before a documented failure start",
        "model_features": MODEL_FEATURES,
        "direct_lps_or_7bar_features_in_learned_models": False,
        "synthetic_contract": {
            "training_rows": len(synthetic),
            "calibration_rows": 0,
            "test_rows": 0,
            "adds_evidence": False,
            "mechanisms": ["downstream_leak", "dryer_drain_open", "reduced_delivery"],
        },
        "simulator": realism,
        "arms": arms,
        "episode_tables": episode_tables,
        "decision": {
            "status": "PROMOTED" if promoted else "NO_PROMOTION",
            "champion": promoted,
            "wrong_physics_control_matches": control_matches,
            "observed_test_episodes": 4,
        },
    }
    OUTPUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    champion = {
        "status": report["decision"]["status"],
        "champion": promoted,
        "target": report["target"],
        "evaluation_origin": "OBSERVED_METROPT3",
        "warning_feed_enabled": bool(promoted),
    }
    CHAMPION.write_text(json.dumps(champion, indent=2), encoding="utf-8")
    if promoted and promoted in fitted:
        joblib.dump(fitted[promoted], MODEL)
    prediction = test[["timestamp", "failure_active", "minutes_to_failure"]].copy()
    for name in arms:
        if name in baseline_test:
            prediction[name] = baseline_test[name]
        elif name in fitted:
            model = fitted[name]
            if name in {"isolation_forest", "pca_residual", "compact_autoencoder"}:
                scorer = unsupervised[name][1]
                prediction[name] = scorer(model, test[MODEL_FEATURES])
            else:
                prediction[name] = model.predict_proba(test[MODEL_FEATURES])[:, 1]
    prediction["data_origin"] = "DERIVED_FROM_OBSERVED"
    PREDICTIONS.parent.mkdir(parents=True, exist_ok=True)
    prediction.to_parquet(PREDICTIONS, index=False)
    print(json.dumps(report["decision"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
