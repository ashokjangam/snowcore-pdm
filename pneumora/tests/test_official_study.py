from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from leak_physics import physics_features
from official_study import Event, alert_times, merged_alerts, random_alerter_null, score_events

ROOT = Path(__file__).resolve().parents[1]


def test_continuous_flags_are_one_alert() -> None:
    times = pd.Series(pd.date_range("2020-03-01", periods=48, freq="5min"))
    assert merged_alerts(times, np.ones(48, dtype=bool)) == [times.iloc[0]]


def test_flags_split_after_merge_gap() -> None:
    times = pd.Series(pd.to_datetime(["2020-03-01 00:00", "2020-03-01 00:25", "2020-03-01 01:30"]))
    assert merged_alerts(times, np.array([True, True, True])) == [times.iloc[0], times.iloc[2]]


def test_loaded_run_grows_only_while_compressor_loaded() -> None:
    stamps = pd.date_range("2020-03-01", periods=360, freq="10s")
    comp = np.ones(360)
    comp[60:300] = 0
    frame = physics_features(pd.DataFrame({"timestamp": stamps, "tp3": 8.5, "comp": comp}))
    runs = frame.set_index("timestamp")["loaded_run_minutes"]
    assert runs.max() >= 39
    assert runs.iloc[0] == 0


def test_persistence_requires_sustained_condition() -> None:
    times = pd.Series(pd.date_range("2020-03-01", periods=30, freq="5min"))
    scores = np.zeros(30)
    scores[5:10] = 10
    assert alert_times(times, scores, 1.0, 12) == []
    scores[5:20] = 10
    assert len(alert_times(times, scores, 1.0, 12)) == 1


def test_caught_in_time_needs_two_hours_before_end() -> None:
    event = Event("T1", pd.Timestamp("2020-04-01 10:00"), pd.Timestamp("2020-04-01 14:00"), "air_leak")
    start, end = pd.Timestamp("2020-03-01"), pd.Timestamp("2020-05-01")
    early = score_events([pd.Timestamp("2020-04-01 11:00")], [event], start, end)
    late = score_events([pd.Timestamp("2020-04-01 12:30")], [event], start, end)
    assert early["caught_in_time"] == 1 and early["false_alerts"] == 0
    assert late["caught_in_time"] == 0 and late["false_alerts"] == 0


def test_random_null_is_a_probability() -> None:
    event = Event("T1", pd.Timestamp("2020-04-01 10:00"), pd.Timestamp("2020-04-01 14:00"), "air_leak")
    result = score_events([pd.Timestamp("2020-04-01 11:00")], [event], pd.Timestamp("2020-03-01"), pd.Timestamp("2020-05-01"))
    null = random_alerter_null(result, 61)
    assert 0 <= null["p_at_least_observed"] <= 1


def test_freeze_predates_external_and_names_gates() -> None:
    freeze = json.loads((ROOT / "autoresearch" / "official_freeze.json").read_text(encoding="utf-8"))
    assert freeze["frozen_before_external_data_was_loaded"] is True
    assert freeze["recipe"]["labels_used_to_fit_or_calibrate"] is False
    assert set(freeze["promotion_gates_external"]) == {
        "air_leaks_caught_in_time",
        "pooled_false_alerts_per_healthy_day",
        "beats_existing_lps_alarm_on_air_leaks",
        "random_alerter_null_all_events",
    }
