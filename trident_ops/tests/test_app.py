from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"
PAGES = [
    "Command Center",
    "Triage + cited RCA",
    "Sensor Evidence",
    "Model Evidence",
    "Flight Recorder",
]


def test_every_page_fails_closed_without_a_snowflake_session() -> None:
    app = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not app.exception
    for page in PAGES:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, (page, [item.value for item in app.exception])
        assert app.title[0].value == page
