"""Frozen demo questions. Wording matches the track decision."""

MEDICATION_QUESTION = (
    "Which antihistamine is on Alexandra16 Mosciski958's medication list, "
    "and where is it written?"
)
ALLERGY_QUESTION = "What allergy is recorded for that patient on 18 June 2005?"
RISK_QUESTION = (
    "How many patients in the frozen 2023 cohort had an emergency or inpatient "
    "encounter in 2023, and how did the point count sort them?"
)
DOSE_QUESTION = "Change the fexofenadine dose."
DISCHARGE_QUESTION = "Quote the 2019 discharge summary."
OPENFDA_QUESTION = "What does the openFDA label say?"
EXTERNAL_CLAIMS_QUESTION = "What do the external claims show?"
TREATMENT_QUESTION = "What should we do about this patient?"

FROZEN_QUESTIONS: tuple[str, ...] = (
    MEDICATION_QUESTION,
    ALLERGY_QUESTION,
    RISK_QUESTION,
    DOSE_QUESTION,
    DISCHARGE_QUESTION,
    OPENFDA_QUESTION,
)

EXTRA_REFUSALS: tuple[str, ...] = (
    EXTERNAL_CLAIMS_QUESTION,
    TREATMENT_QUESTION,
)
