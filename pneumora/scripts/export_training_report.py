"""Export the already-trained campaign as a compact training studio report.

This does not rescore the promotion decision. It records the frozen arms and
fits one diagnostic gradient booster so the studio can show which measured
signals the synthetic-trained model relied on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "autoresearch"))

from run_campaign import (  # noqa: E402
    CALIBRATION_END,
    FEATURES_PATH,
    FIT_END,
    MODEL_FEATURES,
    fit_parameters,
    fit_supervised,
    generate_leaks,
)

CAMPAIGN = ROOT / "autoresearch" / "campaign.json"
OUTPUT = ROOT / "autoresearch" / "training_report.json"


def main() -> int:
    campaign = json.loads(CAMPAIGN.read_text(encoding="utf-8"))
    frame = pd.read_parquet(FEATURES_PATH, columns=["timestamp", "tp3_max_120m", *MODEL_FEATURES]).sort_values("timestamp")
    train = frame[frame["timestamp"] < pd.Timestamp(FIT_END)]
    parameters = fit_parameters(train)
    synthetic = generate_leaks(train, parameters, copies=1)
    model = fit_supervised(train, synthetic)
    observed = train.sample(min(800, len(train)), random_state=42).copy()
    observed["target_failure_2h"] = 0
    sample = pd.concat([observed, synthetic.sample(min(400, len(synthetic)), random_state=42)], ignore_index=True)
    importance = permutation_importance(
        model,
        sample[MODEL_FEATURES],
        sample["target_failure_2h"],
        n_repeats=4,
        random_state=42,
        scoring="neg_brier_score",
    )
    ranked = sorted(
        (
            {"feature": name, "importance": float(value)}
            for name, value in zip(MODEL_FEATURES, importance.importances_mean)
        ),
        key=lambda row: abs(row["importance"]),
        reverse=True,
    )
    arms = []
    for name, arm in campaign["arms"].items():
        observed = arm["observed_test"]
        arms.append(
            {
                "name": name,
                "episodes_warned": observed["episodes_warned_2h"],
                "false_alerts_per_day": observed["false_alerts_per_day"],
                "median_lead_minutes": observed["median_lead_minutes"],
                "gates_pass": all(arm.get("promotion_gates", {}).values()),
                "calibration_alerts_per_day": arm["calibration"]["false_alerts_per_healthy_day"],
            }
        )
    report = {
        "decision": campaign["decision"],
        "split": campaign["split"],
        "target": campaign["target"],
        "trained_rows": {
            "february_feature_windows": int(len(train)),
            "synthetic_training_rows_diagnostic_refit": int(len(synthetic)),
            "calibration_synthetic_rows": 0,
            "test_synthetic_rows": 0,
        },
        "arms": arms,
        "feature_importance": ranked,
        "simulator_passed": campaign["simulator"]["passes_healthy_march_check"],
        "note": "Importance is a diagnostic from the synthetic-trained booster. It is not a promoted model.",
    }
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"decision": report["decision"]["status"], "features": len(ranked)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
