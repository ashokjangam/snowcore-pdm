from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "streamlit" / "app.py"


def test_simple_and_engineering_views_render() -> None:
    if not (ROOT / "data" / "product" / "contract.json").exists():
        pytest.skip("product artifacts not built")
    rendered = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not rendered.exception, [item.value for item in rendered.exception]
    page = " ".join(str(item.value) for item in (*rendered.title, *rendered.markdown, *rendered.info))
    assert "What needs attention now?" in page
    assert "No predictive model passed" in page

    rendered.sidebar.radio[0].set_value("Engineering evidence").run()
    assert not rendered.exception, [item.value for item in rendered.exception]
    page = " ".join(str(item.value) for item in (*rendered.header, *rendered.markdown, *rendered.caption))
    assert "Engineering evidence" in page
    assert "Same replay and warning" in page
