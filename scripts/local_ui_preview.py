"""Local visual harness for streamlit/app.py.

Run:
    streamlit run scripts/local_ui_preview.py

This injects representative, non-production frames behind the Snowpark session
API. It is for layout testing only; deployed metrics still come from Snowflake.
"""

from __future__ import annotations

import datetime as dt
import os
import runpy
import sys
import types
from pathlib import Path

import pandas as pd
import streamlit as st


LINES = ["s_1", "s_2", "s_3", "s_4", "s_5"]


def frame_for(sql: str) -> pd.DataFrame:
    normalized = " ".join(sql.upper().split())

    if "V_EXECUTIVE_KPI" in normalized:
        return pd.DataFrame(
            [
                {
                    "DATA_AS_OF": dt.date(2022, 1, 2),
                    "MODEL_STATUS": "BLIND_TEST_MODEL_OUTPERFORMS_PERSISTENCE",
                    "SITE_WEIGHTED_OEE": 0.4678,
                    "ESTIMATED_MARGIN_EXPOSURE_EUR": 21_387_467,
                    "STOCK_RISK_COUNT": 15,
                }
            ]
        )

    if "V_EXECUTIVE_FLEET" in normalized:
        return pd.DataFrame(
            [
                {
                    "MACHINE_CODE": line,
                    "OEE": oee,
                    "LAST_RISK_SCORE": risk,
                    "RISK_BAND": band,
                    "MODEL_VS_BASELINE_TRUST": trust,
                    "IDLE_HOURS": idle,
                    "BREAKDOWN_HOURS": fault,
                    "MARGIN_EXPOSURE_EUR": exposure,
                }
                for line, oee, risk, band, trust, idle, fault, exposure in [
                    ("s_2", .2885, .6682, "HIGH", "MODEL_OUTPERFORMS_PERSISTENCE", 1869.8, 573.8, 3_460_731),
                    ("s_4", .3745, .5537, "ELEVATED", "MODEL_OUTPERFORMS_PERSISTENCE", 1534.9, 358.4, 4_515_801),
                    ("s_1", .5643, .5206, "ELEVATED", "MODEL_OUTPERFORMS_PERSISTENCE", 1267.1, 1393.4, 4_722_730),
                    ("s_3", .3617, .5129, "ELEVATED", "MODEL_OUTPERFORMS_PERSISTENCE", 2967.0, 466.3, 3_722_839),
                    ("s_5", .5712, .2924, "LOW", "MODEL_DOES_NOT_OUTPERFORM_PERSISTENCE", 2627.1, 355.6, 4_965_367),
                ]
            ]
        )

    if "V_EXECUTIVE_ACTION_QUEUE" in normalized:
        return pd.DataFrame(
            [
                {
                    "ACTION_RANK": i,
                    "PRIORITY": "P1" if i < 4 else "P2",
                    "OWNER_FUNCTION": owner,
                    "MACHINE_CODE": line,
                    "RISK_STATE": state,
                    "PRODUCTION_EXPOSURE_EUR": exposure,
                    "RECOMMENDED_ACTION": recommendation,
                }
                for i, owner, line, state, exposure, recommendation in [
                    (1, "PLANNING", "s_5", "IDLE_DOMINANT", 4_965_367, "Validate schedule, supply and changeover constraints."),
                    (2, "PLANNING", "s_4", "IDLE_DOMINANT", 4_515_801, "Validate schedule, supply and changeover constraints."),
                    (3, "MAINTENANCE", "s_2", "HIGH", 3_460_731, "Review recent alarm pattern and corroborate before inspection."),
                    (4, "SUPPLY_CHAIN", "s_4", "STOCKOUT", 4_515_801, "Review the generic service-kit scenario."),
                ]
            ]
        )

    if "V_OEE_ROLLUP" in normalized:
        if "MACHINE_CODE IS NULL" in normalized:
            return pd.DataFrame(
                [
                    {
                        "MACHINE_CODE": None,
                        "AVAILABILITY": .6432,
                        "PERFORMANCE": .7293,
                        "QUALITY": .9972,
                        "OEE": .4678,
                        "RUN_HOURS": 24_183,
                        "SLOW_RUNNING_HOURS": 4_793,
                        "IDLE_HOURS": 10_266,
                        "BREAKDOWN_HOURS": 3_147,
                    }
                ]
            )
        return pd.DataFrame()

    if "FROM SNOWCORE_REAL.GOLD.WORK_ORDER" in normalized:
        rows = []
        for i in range(16):
            rows.append(
                {
                    "WORK_ORDER_ID": f"WO-B-{2178-i:06d}",
                    "MACHINE_CODE": LINES[i % 5],
                    "CAUSE_CODE": "A_006" if i % 2 else "A_065",
                    "REPORTED_AT": dt.datetime(2022, 1, 1, 4, 0) - dt.timedelta(hours=i),
                    "COMPLETED_AT": dt.datetime(2022, 1, 1, 7, 0) - dt.timedelta(hours=i),
                    "PRIORITY": ["P1", "P2", "P3", "P4"][i % 4],
                    "STATUS": "COMPLETED",
                    "TECH_NAME": ["Lombardi", "Greco", "Esposito"][i % 3],
                    "SPECIALITY": ["Controls", "Mechanical"][i % 2],
                    "LABOUR_COST": 119.55 + i,
                    "PARTS_COST": 7.30 * (i % 3),
                    "LOST_PRODUCTION_COST": 3061 + 100 * i,
                    "TOTAL_COST": 3181 + 100 * i,
                    "DATA_ORIGIN": "SYNTHETIC_IT",
                }
            )
        return pd.DataFrame(rows)

    if "INVENTORY_SNAPSHOT" in normalized:
        return pd.DataFrame(
            [
                {
                    "MATERIAL_ID": f"MAT-B-A_{i:03d}",
                    "SNAPSHOT_DATE": dt.date(2022, 1, 2),
                    "ON_HAND_QTY": i % 5,
                    "REORDER_POINT": 2,
                    "LEAD_TIME_DAYS": 4 + i,
                    "STOCK_STATE": "STOCKOUT" if i < 2 else "AVAILABLE",
                    "DATA_ORIGIN": "SYNTHETIC_ERP",
                }
                for i in range(1, 7)
            ]
        )

    if "DIM_MATERIAL" in normalized:
        return pd.DataFrame(
            [
                {
                    "MATERIAL_ID": f"MAT-B-A_{i:03d}",
                    "ANCHORED_WORK_ORDERS": 4 + i,
                    "MATERIAL_NAME": f"Generic service kit {i}",
                }
                for i in range(1, 7)
            ]
        )

    if "V_DIGITAL_THREAD" in normalized:
        return pd.DataFrame(
            [
                {
                    "SOURCE_EVENT_ID": f"EV-{i:04d}",
                    "STOP_START": dt.datetime(2022, 1, 1, 10, 0) - dt.timedelta(hours=i),
                    "STOP_STATE": "downtime",
                    "ALARM_CODE": "A_006",
                    "OBSERVED_LOSS_MINUTES": 14 + i,
                    "PRODUCTION_ORDER_ID": f"PO-{i:04d}",
                    "ORDER_STATUS": "COMPLETED",
                    "WORK_ORDER_ID": f"WO-{i:04d}",
                    "WORK_ORDER_STATUS": "COMPLETED",
                    "MATERIAL_ID": "MAT-B-A_006",
                    "STOCK_STATE": "REORDER",
                    "EVENT_DATA_ORIGIN": "OBSERVED",
                    "PRODUCTION_ORDER_ORIGIN": "SYNTHETIC_ERP",
                    "WORK_ORDER_ORIGIN": "SYNTHETIC_IT",
                    "PART_ORIGIN": "SYNTHETIC_ERP",
                    "INVENTORY_ORIGIN": "SYNTHETIC_ERP",
                }
                for i in range(8)
            ]
        )

    if "V_PIADE_RESEARCH_TRIALS" in normalized:
        return pd.DataFrame(
            [
                {
                    "TRIAL_NUMBER": i,
                    "MODEL_FAMILY": family,
                    "RUN_STATUS": status,
                    "MEAN_AUC": auc,
                    "WORST_AUC": auc - 0.012,
                    "MEAN_AVG_PRECISION": ap,
                    "MEAN_TOP_DECILE_PRECISION": precision,
                    "MEAN_PERSISTENCE_PRECISION": 0.624,
                    "MEAN_TOP_DECILE_RECALL": 0.17 + i / 1000,
                    "RUNTIME_SECONDS": 38 + i * 3,
                    "CONFIG_JSON": (
                        '{"n_estimators": %d, "max_features": %.2f, '
                        '"min_samples_leaf": %d}'
                        % (300 + i * 20, 0.25 + (i % 5) * 0.1, 10 + (i % 4) * 10)
                    ),
                    "RATIONALE": "Bounded allowlisted trial.",
                    "REJECTION_REASON": None if status == "KEPT" else "Did not improve the guarded objective.",
                }
                for i, family, status, auc, ap, precision in [
                    (1, "EXTRA_TREES", "KEPT", .667, .611, .702),
                    (2, "RANDOM_FOREST", "DISCARDED", .651, .596, .681),
                    (3, "HIST_GRADIENT_BOOSTING", "KEPT", .676, .624, .721),
                    (4, "XGBOOST", "DISCARDED", .671, .619, .713),
                    (5, "LIGHTGBM", "KEPT", .684, .636, .744),
                    (6, "EXTRA_TREES", "DISCARDED", .679, .628, .733),
                ]
            ]
        )

    if "V_PIADE_RESEARCH_CHAMPION" in normalized:
        return pd.DataFrame(
            [
                {
                    "TRIAL_NUMBER": 5,
                    "MODEL_FAMILY": "LIGHTGBM",
                    "MEAN_AUC": .684,
                    "WORST_AUC": .672,
                    "PROMOTION_STATUS": "VALIDATION_CHAMPION",
                }
            ]
        )

    if "V_ASSUMPTIONS_ACTIVE" in normalized:
        return pd.DataFrame(
            [
                {
                    "ASSUMPTION_NAME": "Contribution margin per package",
                    "ASSUMPTION_VALUE": 0.18,
                    "UNIT": "EUR/package",
                    "CLAIM_CLASS": "SYNTHETIC_SCENARIO",
                    "EVIDENCE_NOTE": "Editable illustrative assumption; not present in PIADE.",
                }
            ]
        )

    if "V_MARGIN_SCENARIO_BASE" in normalized:
        return pd.DataFrame(
            [
                {
                    "GRAIN": "SITE",
                    "SUBJECT": "PLANT_B",
                    "ACTUAL_OUTPUT_UNITS": 61_290_000,
                    "DATA_ORIGIN": "OBSERVED_DERIVED",
                }
            ]
        )

    if "V_IMPROVEMENT_LEVERS" in normalized:
        return pd.DataFrame(
            [
                {
                    "LEVER_RANK": rank,
                    "MACHINE_CODE": line,
                    "LOSS_BUCKET": lever,
                    "OBSERVED_FORGONE_PACKAGES": packages,
                    "PCT_OF_SITE_BUCKET_LOSS": share * 100,
                    "OBSERVED_LOSS_HOURS": packages / 4400,
                    "SCENARIO_SIGNED_LOSS_MARGIN_EUR": packages * .18,
                    "EVIDENCE_NOTE": "Historical attribution, not guaranteed recovery.",
                    "CAUSAL_CAVEAT": "Size-of-loss ordering; not causal.",
                }
                for rank, line, lever, packages, share in [
                    (1, "s_2", "Reduce breakdown loss", 3_420_000, .31),
                    (2, "s_3", "Validate idle-time constraints", 2_870_000, .26),
                    (3, "s_4", "Reduce speed loss", 2_110_000, .19),
                    (4, "s_1", "Validate idle-time constraints", 1_640_000, .15),
                ]
            ]
        )

    if "V_ANALYST_DECISION_CONTEXT" in normalized:
        return pd.DataFrame(
            [
                {
                    "TOPIC": "OEE",
                    "SUBJECT": line,
                    "METRIC_NAME": "OEE",
                    "METRIC_VALUE_NUM": value,
                    "UNIT": "RATIO",
                    "CLAIM_CLASS": "OBSERVED_DERIVED",
                    "EVIDENCE_NOTE": "Derived from PIADE production-state records.",
                    "SOURCE_VIEW": "GOLD.V_OEE_ROLLUP",
                }
                for line, value in [("s_1", .5643), ("s_2", .2885), ("s_3", .3617), ("s_4", .3745), ("s_5", .5712)]
            ]
        )

    return pd.DataFrame()


class FakeResult:
    def __init__(self, sql: str):
        self.sql = sql

    def to_pandas(self) -> pd.DataFrame:
        return frame_for(self.sql)


class FakeSession:
    def sql(self, sql: str) -> FakeResult:
        return FakeResult(sql)


snowflake = types.ModuleType("snowflake")
snowpark = types.ModuleType("snowflake.snowpark")
context = types.ModuleType("snowflake.snowpark.context")
context.get_active_session = lambda: FakeSession()
snowflake.snowpark = snowpark
snowpark.context = context
sys.modules["snowflake"] = snowflake
sys.modules["snowflake.snowpark"] = snowpark
sys.modules["snowflake.snowpark.context"] = context

preview_page = os.environ.get("SNOWCORE_PREVIEW_PAGE")
if preview_page and "nav_page" not in st.session_state:
    st.session_state.nav_page = preview_page

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "streamlit" / "app.py"),
    run_name="__main__",
)
