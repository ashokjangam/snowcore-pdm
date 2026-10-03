"""Screen copy that stays on the page without querying a warehouse."""

LEAD = (
    "This is a synthetic chart. Every answer cites a warehouse row, or the page refuses."
)

OUTCOMES: tuple[tuple[str, str], ...] = (
    (
        "Medication citation",
        "A drug on the list is quoted from the chart row and from the clinical-document cell.",
    ),
    (
        "Allergy-code guard",
        "The page quotes the allergy-row code and does not substitute a second code from the same document.",
    ),
    (
        "Honest point count",
        "The 2023 cohort is a frozen point count. It is not a validated risk model.",
    ),
)

BANNER = (
    "Synthetic / non-clinical. These people are Synthea simulations published by MITRE "
    "(108 simulated Massachusetts patients in the paired CSV and C-CDA sample). "
    "Jason Walonoski et al., Synthea: An approach, method, and software mechanism for "
    "generating synthetic patients and the synthetic electronic health care record, "
    "JAMIA 25(3), 2018, 230–238, https://doi.org/10.1093/jamia/ocx079. "
    "MITRE states this synthetic data may be used without restriction for secondary uses "
    "in academia, research, industry, and government. The generator software is Apache-2.0. "
    "Code systems on the rows are licensed separately: SNOMED CT under the NLM U.S. or an "
    "affiliate license, LOINC under the LOINC license, and RxNorm through UMLS. "
    "Not for care. Not a medical device."
)

TRACK_NOTE = (
    "This page is a cited chart plus the frozen point count in CORE.RISK_SCORE. "
    "The point count is not a validated stratifier, not a probability of deterioration, "
    "and not a care recommendation. Queried figures on this page are the figures to rehearse. "
    "A written expected count that disagrees with the query means the load is wrong."
)

POINT_RULES = (
    "The frozen points belong to CORE.RISK_SCORE. This page does not recalculate them: "
    "age at the 2023-01-01 index at least 65; at least one prior emergency or inpatient "
    "encounter; at least 8 conditions active at the index; last prior Hemoglobin A1c "
    "(LOINC 4548-4) at least 6.5. Condition rows include findings, disorders, and "
    "situations, so the condition point is not a disease count. Risk rows are CSV facts "
    "before the index. C-CDA text is not a feature source."
)
