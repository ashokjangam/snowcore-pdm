"""Truth and isolation contracts shared by the TRIDENT OPS app and tests."""

from __future__ import annotations

import json
import re
from typing import Any

PIADE_DATABASE = "SNOWCORE_REAL"
METROPT_DATABASE = "PNEUMORA"
APP_DATABASE = "TRIDENT_OPS"

PIADE_LINES = ("s_1", "s_2", "s_3", "s_4", "s_5")
ALLOWED_ACTIONS = ("ACKNOWLEDGE", "INSPECTION", "SNOOZE")

ORIGIN_LABELS = {
    "OBSERVED": "Observed",
    "OBSERVED_METROPT3": "Observed",
    "DERIVED_FROM_OBSERVED": "Derived",
    "MODEL": "Model",
    "SYNTHETIC_IT": "Scenario",
    "SYNTHETIC_ERP": "Scenario",
    "SYNTHETIC_FACTORY_SCENARIO": "Scenario",
    "OPERATOR_ENTRY": "Operator-entered",
}


def clean_line(value: Any) -> str:
    """Return one of the five published PIADE line ids or fail closed."""
    line = str(value)
    if line not in PIADE_LINES:
        raise ValueError(f"Unknown PIADE line: {line}")
    return line


def clean_action(value: Any) -> str:
    action = str(value).upper()
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported triage action: {action}")
    return action


def sql_literal(value: Any, limit: int = 8_000) -> str:
    text = str(value)[:limit].replace("'", "''")
    return f"'{text}'"


def evidence_label(origin: Any) -> str:
    text = str(origin or "").upper()
    if "SYNTHETIC" in text and ("DERIVED" in text or "OBSERVED" in text):
        return "Mixed: derived + scenario"
    for key, label in ORIGIN_LABELS.items():
        if key in text:
            return label
    return "Unclassified"


def metropt_timing(minutes_after_start: Any, onset_precision: Any) -> tuple[str, str]:
    """Describe alert timing without converting post-onset detection into lead time."""
    if minutes_after_start is None:
        return "No alert", "reactive"
    minutes = float(minutes_after_start)
    if str(onset_precision).lower() == "day":
        return f"{abs(minutes):.0f} min into logged day; exact onset unknown", "uncertain"
    if minutes < 0:
        return f"{abs(minutes):.0f} min before logged onset", "forecast"
    return f"{minutes:.0f} min after logged onset", "detection"


def rca_prompt(line: str, records: list[dict[str, Any]]) -> str:
    """Bound Cortex to deterministic evidence and force abstention."""
    line = clean_line(line)
    allowed = []
    for record in records[:5]:
        allowed.append(
            {
                key: record.get(key)
                for key in (
                    "ALARM_CODE",
                    "LONG_BREAKDOWNS",
                    "BREAKDOWN_HOURS",
                    "MEDIAN_STOP_MIN",
                    "PRECURSOR_RATE",
                    "REPEAT_24H_RATE",
                    "BACK_TO_RUNNING_RATE",
                    "WAITING_AFTER_RATE",
                    "PATTERN",
                )
            }
        )
    return (
        "You are the TRIDENT OPS evidence narrator. Use only the JSON evidence below. "
        "The alarm codes are anonymised, so never invent a component, physical root cause, "
        "technician finding, price, saving, or trend. Explain the strongest observed pattern, "
        "cite the alarm code and numbers used, and state what "
        "cannot be known. If the question concerns another plant or a compressor, abstain. "
        "The next_question must be exactly one sentence that starts 'At the next planned stop, "
        "can the team verify' and asks the team to verify an observable alarm sequence or line "
        "state; it must not guess a component or ask for general scheduling context. "
        f"PIADE line={line}. Evidence={json.dumps(allowed, default=str)}"
    )


def contains_cross_plant_join(sql: str) -> bool:
    """Catch executable statements that mention both databases."""
    stripped = re.sub(r"/\*.*?\*/|--[^\n]*", " ", sql, flags=re.DOTALL)
    statements = re.split(r";", stripped)
    return any(
        PIADE_DATABASE in statement.upper() and METROPT_DATABASE in statement.upper()
        for statement in statements
    )
