from __future__ import annotations

from pathlib import Path

from modules.contracts import contains_cross_plant_join

ROOT = Path(__file__).resolve().parents[2]


def test_no_sql_statement_joins_the_two_source_plants() -> None:
    files = list((ROOT / "trident_ops" / "sql").glob("*.sql"))
    files += list((ROOT / "pneumora" / "sql").glob("*.sql"))
    files += [path for path in (ROOT / "sql").glob("*.sql") if not path.name.startswith("_")]
    violations = [
        str(path.relative_to(ROOT))
        for path in files
        if contains_cross_plant_join(path.read_text(encoding="utf-8"))
    ]
    assert violations == []


def test_new_app_does_not_claim_a_unified_asset_model() -> None:
    app = (ROOT / "trident_ops" / "app.py").read_text(encoding="utf-8").lower()
    assert "zero fabricated joins" in app
    assert "no-join firewall" in app
    assert "cross_validated_not_promoted" in app
    assert "usually alerts after the leak starts" in app
    assert "scenario exposure only" in app
    assert '"source": "co-pilot"' not in app
    assert '"source": "trident detector"' in app


def test_triage_procedure_is_idempotent_and_plant_scoped() -> None:
    sql = (ROOT / "trident_ops" / "sql" / "01_triage_action.sql").read_text(encoding="utf-8").upper()
    assert "MERGE INTO TRIDENT_OPS.OPS.TRIAGE_ACTION" in sql
    assert "IDEMPOTENCY_KEY" in sql
    assert "P_PLANT_CODE <> 'PLANT_B'" in sql
    assert "P_MACHINE_CODE NOT IN ('S_1','S_2','S_3','S_4','S_5')" in sql
