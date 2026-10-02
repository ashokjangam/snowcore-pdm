from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "streamlit" / "app.py"


def test_simple_and_engineering_modes_share_one_app() -> None:
    source = APP.read_text(encoding="utf-8")
    assert '"Simple", "Engineering evidence"' in source
    assert "What needs attention now?" in source
    assert "Why this warning" in source


def test_app_discloses_synthetic_and_unvalidated_outputs() -> None:
    source = APP.read_text(encoding="utf-8")
    assert "Synthetic maintenance record" in source
    assert "not validated RUL" in source
    assert "not this train's real production" in source
    assert "Row-wise accuracy is intentionally not shown" in source
