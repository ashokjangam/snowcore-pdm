from __future__ import annotations

import json

import pytest

from modules.contracts import (
    clean_action,
    clean_line,
    contains_cross_plant_join,
    evidence_label,
    metropt_timing,
    rca_prompt,
)


def test_piade_inputs_fail_closed() -> None:
    assert clean_line("s_3") == "s_3"
    assert clean_action("inspection") == "INSPECTION"
    with pytest.raises(ValueError):
        clean_line("APU-01")
    with pytest.raises(ValueError):
        clean_action("DELETE")


def test_metropt_timing_never_calls_post_onset_a_forecast() -> None:
    assert metropt_timing(45, "minute") == ("45 min after logged onset", "detection")
    assert metropt_timing(-80, "minute") == ("80 min before logged onset", "forecast")
    label, lane = metropt_timing(80, "day")
    assert "exact onset unknown" in label
    assert lane == "uncertain"


def test_rca_prompt_is_bounded_and_forbids_invention() -> None:
    rows = [
        {
            "ALARM_CODE": "A_065",
            "BREAKDOWN_HOURS": 22.4,
            "PATTERN": "SHORT_STOPS_COME_FIRST",
            "FORBIDDEN_RAW_FIELD": "must not leave the contract",
        }
    ] * 8
    prompt = rca_prompt("s_1", rows)
    assert "never invent" in prompt
    assert "another plant or a compressor, abstain" in prompt
    assert "FORBIDDEN_RAW_FIELD" not in prompt
    evidence = json.loads(prompt.split("Evidence=", 1)[1])
    assert len(evidence) == 5


def test_evidence_labels_are_explicit() -> None:
    assert evidence_label("DERIVED_FROM_OBSERVED + SYNTHETIC_ERP") == "Mixed: derived + scenario"
    assert evidence_label("SYNTHETIC_FACTORY_SCENARIO") == "Scenario"
    assert evidence_label("OPERATOR_ENTRY") == "Operator-entered"


def test_cross_plant_sql_detector() -> None:
    bad = "SELECT * FROM SNOWCORE_REAL.GOLD.X JOIN PNEUMORA.ML.Y ON 1=1;"
    good = "SELECT * FROM SNOWCORE_REAL.GOLD.X; SELECT * FROM PNEUMORA.ML.Y;"
    comment_only = "-- SNOWCORE_REAL and PNEUMORA stay separate\nSELECT 1;"
    assert contains_cross_plant_join(bad)
    assert not contains_cross_plant_join(good)
    assert not contains_cross_plant_join(comment_only)
