from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "sis" / "app.py"
EXPORT = ROOT / "data" / "snowflake"
PAGES = ["What needs attention", "Leak copilot", "Work orders", "Compressor health", "Engineering evidence"]

pytestmark = pytest.mark.skipif(not (EXPORT / "manifest.json").exists(), reason="run scripts/export_snowflake.py first")


def exported(name: str) -> pd.DataFrame:
    frame = pd.read_csv(EXPORT / f"{name}.csv.gz")
    frame.columns = [column.lower() for column in frame.columns]
    return frame


def test_snowflake_status_rules_match_the_local_server_at_random_moments() -> None:
    from fastapi.testclient import TestClient

    from server.main import app

    sys.path.insert(0, str(ROOT / "sis"))
    from status_rules import status_at

    telemetry = exported("telemetry_5m")
    telemetry["ts"] = pd.to_datetime(telemetry["ts"])
    telemetry = telemetry.set_index("ts").sort_index()
    orders = exported("work_orders")
    orders["created_at"] = pd.to_datetime(orders["created_at"])
    client = TestClient(app)
    rng = np.random.default_rng(7)
    start, end = telemetry.index.min(), telemetry.index.max()
    moments = [start + (end - start) * float(f) for f in rng.uniform(size=40)]
    moments += [pd.Timestamp(t) for t in exported("alerts").query("source == 'copilot'")["raised_at"]]
    for moment in moments:
        moment = pd.Timestamp(moment).floor("5min")
        server = client.get("/api/now", params={"at": moment.isoformat()}).json()
        mine = status_at(moment, telemetry, orders, 60)
        assert (mine["state"], mine["title"], mine["decided_by"]) == (server["state"], server["title"], server["decided_by"]), moment


def test_every_page_renders_from_the_export() -> None:
    from streamlit.testing.v1 import AppTest

    rendered = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not rendered.exception, [item.value for item in rendered.exception]
    for page in PAGES:
        rendered.sidebar.radio(key="page").set_value(page).run()
        assert not rendered.exception, (page, [item.value for item in rendered.exception])
        assert rendered.title[0].value == page


def test_prediction_cases_match_the_scored_study() -> None:
    import json

    study = json.loads((ROOT / "autoresearch" / "prediction_study.json").read_text(encoding="utf-8"))
    recorded = {e["event_id"]: e for fold in study["folds"] for e in fold["events"]}
    cases = exported("prediction_cases")
    assert len(cases) == len(recorded) == 9
    for row in cases.itertuples():
        assert bool(row.predicted_in_time) == recorded[row.event_id]["caught_in_time"], row.event_id
    assert int(cases.loc[cases["kind"] == "air_leak", "predicted_in_time"].sum()) == study["held_out_pooled"]["air_caught"]
    assert set(exported("prediction_zoom")["case_id"]) == set(cases["case_id"])


def test_work_orders_can_be_created_without_duplicates() -> None:
    sql = (ROOT / "sql" / "06_work_orders.sql").read_text(encoding="utf-8").upper()
    assert "PROCEDURE PNEUMORA.OPS.CREATE_WORK_ORDER" in sql and "'DEDUPLICATED', TRUE" in sql
    assert "PROCEDURE PNEUMORA.OPS.SET_WORK_ORDER_STATUS" in sql
    source = APP.read_text(encoding="utf-8")
    assert "OPS.CREATE_WORK_ORDER" in source and "Create work order" in source


def test_next_alert_button_moves_the_replay_to_a_copilot_alert() -> None:
    from streamlit.testing.v1 import AppTest

    rendered = AppTest.from_file(str(APP), default_timeout=120).run()
    rendered.sidebar.button[1].click().run()
    assert not rendered.exception
    moment = pd.Timestamp.combine(rendered.session_state["replay_day"], rendered.session_state["replay_time"])
    assert moment == pd.Timestamp("2020-06-06 20:45")
    page = " ".join(str(item.value) for item in rendered.markdown)
    assert "Possible air leak" in page
