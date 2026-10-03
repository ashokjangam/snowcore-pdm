"""Which warehouse steps a question needs. The page executes the steps."""

from __future__ import annotations

from typing import assert_never

from app.intents import classify_intent, refusal_intents
from app.models import Intent
from app.text_parse import synthea_name


def retrieval_steps(question: str, selected_patient_id: str | None) -> tuple[str, ...]:
    """Ordered query names. A refusal has no query."""
    if refusal_intents(question):
        return ()
    intent = classify_intent(question)
    if intent is Intent.NO_CITATION:
        return ()
    if intent is Intent.RISK_COHORT:
        return ("risk",)
    if intent is Intent.MEDICATION_CITATION:
        if synthea_name(question) is None and not selected_patient_id:
            return ()
        steps = ["patient_name"] if synthea_name(question) is not None else []
        steps.extend(["antihistamine", "medication_section"])
        return tuple(steps)
    if intent is Intent.ALLERGY_CITATION:
        if synthea_name(question) is None and not selected_patient_id:
            return ()
        steps = ["patient_name"] if synthea_name(question) is not None else []
        steps.extend(["allergy", "allergy_section"])
        return tuple(steps)
    if intent in {
        Intent.REFUSE_MEDICATION_CHANGE,
        Intent.REFUSE_DISCHARGE,
        Intent.REFUSE_EXTERNAL,
        Intent.REFUSE_TREATMENT,
    }:
        return ()
    assert_never(intent)
