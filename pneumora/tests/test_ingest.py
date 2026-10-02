from __future__ import annotations

import numpy as np
import pandas as pd

from ingest_metropt import build_features, failure_table, label_observed, normalise_name
from pneumora.contracts import ANALOG_SIGNALS, DIGITAL_SIGNALS, OBSERVED


def telemetry(periods: int = 80) -> pd.DataFrame:
    timestamps = pd.date_range("2020-04-17 20:00", periods=periods, freq="10min")
    frame = pd.DataFrame({"timestamp": timestamps})
    for index, column in enumerate(ANALOG_SIGNALS):
        frame[column] = 5 + index + np.sin(np.arange(periods) / 8)
    for index, column in enumerate(DIGITAL_SIGNALS):
        frame[column] = (np.arange(periods) + index) % 2
    frame["data_origin"] = OBSERVED
    frame["source_dataset"] = "METROPT3_UCI_791"
    return frame


def test_normalise_published_column_names() -> None:
    assert normalise_name("DV eletric") == "dv_electric"
    assert normalise_name("Oil Temperature") == "oil_temperature"
    assert normalise_name("Caudal Impulses") == "caudal_impulses"


def test_failure_labels_are_observed_and_time_based() -> None:
    failures = failure_table()
    labelled = label_observed(telemetry(), failures)
    assert set(failures["data_origin"]) == {OBSERVED}
    assert labelled["failure_active"].sum() > 0
    before = labelled[labelled["timestamp"] < failures.iloc[0]["start"]]
    assert before["minutes_to_failure"].dropna().min() >= 0


def test_feature_windows_remain_derived() -> None:
    features = build_features(label_observed(telemetry(200), failure_table()))
    assert not features.empty
    assert set(features["data_origin"]) == {"DERIVED_FROM_OBSERVED"}
    assert {"loaded_fraction_2h", "cycle_starts_2h", "tp3_reservoir_gap"} <= set(features)
