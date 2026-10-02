from __future__ import annotations

import pandas as pd

from build_product import build_work_orders, factory_scenario


def test_work_orders_are_synthetic_and_actionable() -> None:
    warnings = pd.DataFrame(
        {
            "warning_id": ["PN-W-00001"],
            "raised_at": [pd.Timestamp("2020-06-05 09:00")],
            "risk_level": ["ATTENTION"],
        }
    )
    orders = build_work_orders(warnings)
    assert set(orders["data_origin"]) == {"SYNTHETIC_MAINTENANCE"}
    assert orders.iloc[0]["first_action"]
    assert orders.iloc[0]["plain_problem"]


def test_factory_score_is_always_labelled_synthetic() -> None:
    kpis = pd.DataFrame(
        {
            "date": pd.date_range("2020-02-01", periods=3),
            "time_under_strain": [0.0, 0.1, 0.2],
        }
    )
    scenario = factory_scenario(kpis)
    assert set(scenario["data_origin"]) == {"SYNTHETIC_FACTORY_SCENARIO"}
    assert scenario["disclaimer"].str.contains("not this train").all()
    assert scenario["oee"].between(0, 1).all()
