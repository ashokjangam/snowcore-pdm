from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "autoresearch" / "precursor_study.json"


def test_precursor_study_declares_gates_and_keeps_a_no_leak_control() -> None:
    study = json.loads(STUDY.read_text(encoding="utf-8"))
    assert set(study["declared_gates"]) == {
        "pre_onset_three_of_nine", "false_alert_budget", "beats_random_bonferroni", "beats_existing_alarm_pre_onset",
    }
    assert set(study["summary"]) == {"label_free_cycle_physics", "gbm_precursor", "gbm_onset", "gbm_replay"}
    assert study["exploratory_rolling_baseline"]["status"] == "EXPLORATORY_POST_HOC_NOT_PROMOTABLE"
    curve = study["injection_sensitivity"]["curve"]
    assert curve[0]["leak_fraction_of_normal_idle_decay"] == 0.0
    assert "SYNTHETIC_TRAINING_ONLY" in study["injection_sensitivity"]["origin"]


def test_product_never_claims_prediction_the_study_did_not_promote() -> None:
    precursor = json.loads(STUDY.read_text(encoding="utf-8"))
    prediction = json.loads((ROOT / "autoresearch" / "prediction_study.json").read_text(encoding="utf-8"))
    app = (ROOT / "sis" / "app.py").read_text(encoding="utf-8")
    if not precursor["any_promoted"]:
        assert "It predicts the breakdown, not the leak" in app
        assert "predicts the leak" not in app.lower()
    if prediction["status"] != "PROMOTED_CROSS_VALIDATED":
        assert "promoted, cross-validated" not in app


def test_prediction_study_declares_gates_before_scoring_and_states_its_revision() -> None:
    study = json.loads((ROOT / "autoresearch" / "prediction_study.json").read_text(encoding="utf-8"))
    source = (ROOT / "autoresearch" / "prediction_study.py").read_text(encoding="utf-8")
    assert set(study["declared_gates"]) == set(study["gates"]) == {
        "air_predictions_beat_existing_alarm", "no_fold_worse_than_existing_alarm", "false_alert_budget",
        "beats_random_alerter", "useful_lead",
    }
    assert study["status"] == ("PROMOTED_CROSS_VALIDATED" if all(study["gates"].values()) else "NO_PROMOTION")
    assert "oil_residual" not in source.split("FAMILIES")[1].split("def ")[0]
    assert "not an untouched test" in study["caveat"]


def test_visible_text_never_says_co_pilot() -> None:
    for path in (ROOT / "sis" / "app.py", ROOT / "sis" / "status_rules.py", ROOT / "server" / "main.py", ROOT / "web" / "app.js"):
        assert not re.search(r"co-pilot", path.read_text(encoding="utf-8"), re.IGNORECASE), path


def test_operator_decisions_are_idempotent() -> None:
    sql = (ROOT / "sql" / "04_actions.sql").read_text(encoding="utf-8").upper()
    assert "MERGE INTO PNEUMORA.OPS.ACTION_LOG" in sql
    assert "ON TARGET.IDEMPOTENCY_KEY = SOURCE.IDEMPOTENCY_KEY" in sql
    assert "('ACKNOWLEDGE', 'INSPECT', 'DISMISS')" in sql


def test_native_ml_trains_before_any_failure_and_stays_inside_pneumora() -> None:
    sql = (ROOT / "sql" / "05_native_ml.sql").read_text(encoding="utf-8")
    assert "SNOWFLAKE.ML.ANOMALY_DETECTION" in sql
    assert "WHERE TS < '2020-04-01'" in sql
    assert "'prediction_interval': 0.99" in sql
    for path in (ROOT / "sql").glob("*.sql"):
        text = path.read_text(encoding="utf-8").upper()
        assert "SNOWCORE" not in text.replace("NO SNOWCORE_", ""), path
        assert "TRIDENT_OPS" not in text, path
