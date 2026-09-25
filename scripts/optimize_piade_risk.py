"""Honest model search for PIADE next-hour heavy-stop risk.

This is an offline development harness, not the production scoring job. Model
selection uses two rolling-origin validation windows: April–July 2021 and
August–November 2021. December 2021 onward is held back for the one-shot final
evaluation. The winner can then be ported to ``sql/15_plant_b_risk.sql``.

The script intentionally reports the persistence baseline beside every model.
A higher score than the base rate is not enough: a useful model must improve
on the cheap rule "the line is stopping now, so it may stop next hour too".
"""

from __future__ import annotations

import json
import pathlib
import time
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score


ROOT = pathlib.Path(__file__).resolve().parents[1]
HOURLY = ROOT / "data" / "raw" / "piade" / "sequences_1h_data.csv"
RESULT = ROOT / "docs" / "piade-model-search.json"

VALIDATION_START = pd.Timestamp("2021-04-01")
SECOND_VALIDATION_START = pd.Timestamp("2021-08-01")
FINAL_TEST_START = pd.Timestamp("2021-12-01")
SEED = 20260925

STATE_COLS = [
    "%idle",
    "%production",
    "%downtime",
    "%performance_loss",
    "%scheduled_downtime",
]


@dataclass
class Score:
    model: str
    split: str
    rows: int
    positive_rate: float
    auc: float
    average_precision: float
    top_decile_precision: float
    top_decile_recall: float
    baseline_auc: float
    baseline_average_precision: float
    baseline_top_decile_precision: float
    seconds: float


def top_fraction(y: pd.Series, score: np.ndarray, fraction: float = 0.10) -> tuple[float, float]:
    """Precision/recall for exactly the highest-scored fraction of rows."""
    take = max(1, int(np.ceil(len(score) * fraction)))
    chosen = np.argsort(-np.asarray(score), kind="stable")[:take]
    hits = int(y.iloc[chosen].sum())
    return hits / take, hits / int(y.sum()) if y.sum() else 0.0


def engineer() -> tuple[pd.DataFrame, list[str]]:
    raw = pd.read_csv(HOURLY)
    raw["interval_start"] = pd.to_datetime(raw["interval_start"], format="ISO8601")
    raw = raw.sort_values(["equipment_ID", "interval_start"]).reset_index(drop=True)

    alarm_cols = [c for c in raw.columns if c.startswith("A_")]
    transition_cols = [c for c in raw.columns if "/" in c]
    numeric_source = STATE_COLS + ["#changes", "count_sum"] + alarm_cols + transition_cols
    raw[numeric_source] = raw[numeric_source].apply(pd.to_numeric, errors="coerce").fillna(0)

    frames: list[pd.DataFrame] = []
    for _, machine in raw.groupby("equipment_ID", sort=True):
        g = machine.copy()
        g["run_frac"] = g["%production"] + g["%performance_loss"]
        g["alarm_total"] = g[alarm_cols].sum(axis=1)
        g["alarm_distinct"] = (g[alarm_cols] > 0).sum(axis=1)
        g["transition_total"] = g[transition_cols].sum(axis=1)

        # Compact history features.  Every window ends at the current hour.
        history_sources = [
            "%downtime",
            "%idle",
            "run_frac",
            "alarm_total",
            "alarm_distinct",
            "#changes",
            "count_sum",
        ]
        for col in history_sources:
            for window in (3, 6, 12, 24, 72):
                rolling = g[col].rolling(window, min_periods=1)
                g[f"{col}_mean_{window}"] = rolling.mean()
                if window in (12, 24, 72):
                    g[f"{col}_max_{window}"] = rolling.max()
                    g[f"{col}_std_{window}"] = rolling.std().fillna(0)
            for lag in (1, 2, 3, 6, 12, 24):
                g[f"{col}_lag_{lag}"] = g[col].shift(lag)

        # Changes are often more transferable between machines than levels.
        g["downtime_accel_3_24"] = (
            g["%downtime_mean_3"] - g["%downtime_mean_24"]
        )
        g["run_accel_3_24"] = g["run_frac_mean_3"] - g["run_frac_mean_24"]
        g["alarm_accel_3_24"] = g["alarm_total_mean_3"] - g["alarm_total_mean_24"]
        g["hours_since_heavy_stop"] = (
            g.groupby((g["%downtime"] > 0.10).cumsum()).cumcount()
        )
        g["gap_hours"] = (
            g["interval_start"].diff().dt.total_seconds().div(3600).fillna(-1)
        )

        # Shift/calendar context is known at scoring time.  Sine/cosine avoids
        # teaching the model that hour 23 is far from hour 0.
        hour = g["interval_start"].dt.hour
        dow = g["interval_start"].dt.dayofweek
        g["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        g["hour_cos"] = np.cos(2 * np.pi * hour / 24)
        g["dow_sin"] = np.sin(2 * np.pi * dow / 7)
        g["dow_cos"] = np.cos(2 * np.pi * dow / 7)
        for code in sorted(raw["equipment_ID"].unique()):
            g[f"machine_{code}"] = (g["equipment_ID"] == code).astype(int)

        next_downtime = g["%downtime"].shift(-1)
        g["label"] = (next_downtime > 0.10).astype(int)
        g["baseline"] = g["%downtime"]
        g = g.iloc[:-1]  # no label exists for the last machine-hour
        frames.append(g)

    full = pd.concat(frames, ignore_index=True)
    excluded = {
        "interval_start",
        "equipment_ID",
        "label",
        "baseline",
    }
    features = [
        c
        for c in full.columns
        if c not in excluded and pd.api.types.is_numeric_dtype(full[c])
    ]
    full[features] = full[features].replace([np.inf, -np.inf], np.nan).fillna(0)
    return full, features


def evaluate(name: str, model, train: pd.DataFrame, scored: pd.DataFrame, features: list[str], split: str) -> Score:
    started = time.perf_counter()
    model.fit(train[features], train["label"])
    probability = model.predict_proba(scored[features])[:, 1]
    elapsed = time.perf_counter() - started
    y = scored["label"].astype(int)
    baseline = scored["baseline"].to_numpy()
    precision, recall = top_fraction(y, probability)
    baseline_precision, _ = top_fraction(y, baseline)
    return Score(
        model=name,
        split=split,
        rows=len(scored),
        positive_rate=float(y.mean()),
        auc=float(roc_auc_score(y, probability)),
        average_precision=float(average_precision_score(y, probability)),
        top_decile_precision=float(precision),
        top_decile_recall=float(recall),
        baseline_auc=float(roc_auc_score(y, baseline)),
        baseline_average_precision=float(average_precision_score(y, baseline)),
        baseline_top_decile_precision=float(baseline_precision),
        seconds=elapsed,
    )


def candidates() -> list[tuple[str, object]]:
    return [
        (
            "hist_depth6_l2",
            HistGradientBoostingClassifier(
                learning_rate=0.06,
                max_iter=300,
                max_leaf_nodes=31,
                max_depth=6,
                min_samples_leaf=35,
                l2_regularization=2.0,
                early_stopping=True,
                validation_fraction=0.15,
                random_state=SEED,
            ),
        ),
        (
            "hist_depth8_l5",
            HistGradientBoostingClassifier(
                learning_rate=0.045,
                max_iter=400,
                max_leaf_nodes=47,
                max_depth=8,
                min_samples_leaf=45,
                l2_regularization=5.0,
                early_stopping=True,
                validation_fraction=0.15,
                random_state=SEED,
            ),
        ),
        (
            "extra_leaf8",
            ExtraTreesClassifier(
                n_estimators=500,
                max_features=0.7,
                min_samples_leaf=8,
                class_weight="balanced",
                n_jobs=-1,
                random_state=SEED,
            ),
        ),
        (
            "extra_leaf20",
            ExtraTreesClassifier(
                n_estimators=500,
                max_features=0.7,
                min_samples_leaf=20,
                class_weight="balanced",
                n_jobs=-1,
                random_state=SEED,
            ),
        ),
        (
            "extra_leaf12_mf04",
            ExtraTreesClassifier(
                n_estimators=700,
                max_features=0.4,
                min_samples_leaf=12,
                class_weight="balanced",
                n_jobs=-1,
                random_state=SEED,
            ),
        ),
        (
            "extra_leaf30_mf04",
            ExtraTreesClassifier(
                n_estimators=700,
                max_features=0.4,
                min_samples_leaf=30,
                class_weight="balanced",
                n_jobs=-1,
                random_state=SEED,
            ),
        ),
        (
            "extra_leaf12_all",
            ExtraTreesClassifier(
                n_estimators=700,
                max_features=1.0,
                min_samples_leaf=12,
                class_weight="balanced",
                n_jobs=-1,
                random_state=SEED,
            ),
        ),
    ]


def main() -> None:
    full, features = engineer()
    development_1 = full[full["interval_start"] < VALIDATION_START]
    validation_1 = full[
        (full["interval_start"] >= VALIDATION_START)
        & (full["interval_start"] < SECOND_VALIDATION_START)
    ]
    development_2 = full[full["interval_start"] < SECOND_VALIDATION_START]
    validation_2 = full[
        (full["interval_start"] >= SECOND_VALIDATION_START)
        & (full["interval_start"] < FINAL_TEST_START)
    ]
    final_test = full[full["interval_start"] >= FINAL_TEST_START]

    print(
        f"rows={len(full):,} features={len(features)} "
        f"fold1={len(development_1):,}/{len(validation_1):,} "
        f"fold2={len(development_2):,}/{len(validation_2):,} "
        f"final_test={len(final_test):,}"
    )

    validation_scores: list[Score] = []
    for name, model in candidates():
        score_1 = evaluate(
            name, model, development_1, validation_1, features, "validation_1"
        )
        # Recreate the estimator; scikit estimators are stateful after fit.
        model_2 = dict(candidates())[name]
        score_2 = evaluate(
            name, model_2, development_2, validation_2, features, "validation_2"
        )
        validation_scores.extend([score_1, score_2])
        print(asdict(score_1))
        print(asdict(score_2))

    # Select without consulting December.  Mean AUC across two rolling-origin
    # folds is primary; fixed-workload precision breaks near-ties.
    leaderboard = (
        pd.DataFrame([asdict(s) for s in validation_scores])
        .groupby("model", as_index=False)
        .agg(
            mean_auc=("auc", "mean"),
            worst_auc=("auc", "min"),
            mean_top_decile_precision=("top_decile_precision", "mean"),
            worst_top_decile_precision=("top_decile_precision", "min"),
        )
        .sort_values(
            ["mean_auc", "worst_auc", "mean_top_decile_precision"],
            ascending=False,
        )
    )
    print(leaderboard.to_string(index=False))
    winner_name = str(leaderboard.iloc[0]["model"])
    winner_model = dict(candidates())[winner_name]
    train = full[full["interval_start"] < FINAL_TEST_START]
    final_score = evaluate(
        winner_name, winner_model, train, final_test, features, "final_test"
    )
    print("WINNER", winner_name)
    print("FINAL", asdict(final_score))

    payload = {
        "selection_rule": "highest mean AUC across two rolling-origin validation folds; worst-fold AUC and mean top-decile precision break ties",
        "validation_start": str(VALIDATION_START),
        "second_validation_start": str(SECOND_VALIDATION_START),
        "final_test_start": str(FINAL_TEST_START),
        "feature_count": len(features),
        "validation_scores": [asdict(s) for s in validation_scores],
        "leaderboard": leaderboard.to_dict(orient="records"),
        "winner": winner_name,
        "final_score": asdict(final_score),
    }
    RESULT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"wrote {RESULT}")


if __name__ == "__main__":
    main()
