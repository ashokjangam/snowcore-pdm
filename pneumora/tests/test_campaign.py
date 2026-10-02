from __future__ import annotations

import numpy as np
import pandas as pd

from run_campaign import calibrate_threshold, evaluate, merged_alerts


def test_alerts_merge_within_thirty_minutes() -> None:
    times = pd.Series(pd.to_datetime(["2020-03-01 00:00", "2020-03-01 00:20", "2020-03-01 01:00"]))
    assert merged_alerts(times, np.array([True, True, True])) == [times.iloc[0], times.iloc[2]]


def test_calibration_freezes_to_workload_budget() -> None:
    times = pd.Series(pd.date_range("2020-03-01", periods=31 * 24, freq="h"))
    scores = np.linspace(0, 1, len(times))
    _, report = calibrate_threshold(times, scores)
    assert report["false_alerts_per_healthy_day"] <= report["budget"]


def test_observed_evaluation_is_episode_level() -> None:
    times = pd.Series(
        pd.to_datetime(
            [
                "2020-04-17 23:00",
                "2020-05-29 22:30",
                "2020-06-05 09:00",
                "2020-07-15 13:30",
            ]
        )
    )
    result, episodes = evaluate(times, np.ones(4), 0.5)
    assert result["episodes_warned_2h"] == 4
    assert result["evaluation_origin"] == "OBSERVED_METROPT3"
    assert len(episodes) == 4
