from __future__ import annotations

import numpy as np
import pandas as pd

from run_campaign import MODEL_FEATURES
from simulator import fit_parameters, generate_leaks, realism_report


def feature_frame(rows: int = 200) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    frame = pd.DataFrame({column: rng.normal(1, 0.1, rows) for column in MODEL_FEATURES})
    frame["loaded_fraction_2h"] = rng.uniform(0.2, 0.7, rows)
    frame["cycle_starts_2h"] = rng.integers(1, 10, rows)
    frame["tp3_max_120m"] = rng.normal(9, 0.2, rows)
    return frame


def test_synthetic_rows_are_training_only_and_deterministic() -> None:
    observed = feature_frame()
    parameters = fit_parameters(observed)
    first = generate_leaks(observed, parameters, copies=1, seed=3)
    second = generate_leaks(observed, parameters, copies=1, seed=3)
    assert first[MODEL_FEATURES].equals(second[MODEL_FEATURES])
    assert set(first["data_origin"]) == {"SYNTHETIC_TRAINING_ONLY"}
    assert set(first["target_failure_2h"]) == {1}


def test_physics_injection_increases_loaded_fraction() -> None:
    observed = feature_frame()
    generated = generate_leaks(observed, fit_parameters(observed), copies=1)
    assert generated["loaded_fraction_2h"].median() > observed["loaded_fraction_2h"].median()


def test_wrong_physics_is_an_explicit_negative_control() -> None:
    observed = feature_frame()
    generated = generate_leaks(observed, fit_parameters(observed), copies=1, wrong_physics=True)
    assert set(generated["synthetic_mechanism"]) == {"wrong_channel_control"}


def test_realism_check_uses_heldout_healthy_data() -> None:
    observed = feature_frame()
    report = realism_report(observed, observed.copy(), fit_parameters(observed))
    assert report["passes_healthy_march_check"]
