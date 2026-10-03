"""Shared answer and citation types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union


class Intent(Enum):
    """Question classes the page can answer or refuse."""

    MEDICATION_CITATION = "medication_citation"
    ALLERGY_CITATION = "allergy_citation"
    RISK_COHORT = "risk_cohort"
    REFUSE_MEDICATION_CHANGE = "refuse_medication_change"
    REFUSE_DISCHARGE = "refuse_discharge"
    REFUSE_EXTERNAL = "refuse_external"
    REFUSE_TREATMENT = "refuse_treatment"
    NO_CITATION = "no_citation"


class AnswerStatus(Enum):
    """Whether retrieved rows supported a citation tuple."""

    CITED = "cited"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True)
class DocumentCitation:
    """C-CDA citation. Element ids restart across files, so document_id stays."""

    document_id: str
    section_loinc: str
    element_id: str

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.document_id, self.section_loinc, self.element_id)


@dataclass(frozen=True, slots=True)
class TableCitation:
    """Structured-row citation. Clinical tables in this sample have no row id."""

    table: str
    patient_id: str
    encounter_id: str
    code: str
    start: str

    def as_tuple(self) -> tuple[str, str, str, str, str]:
        return (self.table, self.patient_id, self.encounter_id, self.code, self.start)


@dataclass(frozen=True, slots=True)
class CohortCitation:
    """Risk-view citation. The cohort question has no patient row to invent."""

    table: str
    index_date: str
    horizon_end: str
    score: str

    def as_tuple(self) -> tuple[str, str, str, str]:
        return (self.table, self.index_date, self.horizon_end, self.score)


Citation = Union[DocumentCitation, TableCitation, CohortCitation]


@dataclass(frozen=True, slots=True)
class Answer:
    """Deterministic answer. Narration is allowed only when a citation exists."""

    status: AnswerStatus
    intent: Intent
    text: str
    citations: tuple[Citation, ...]
    narration_allowed: bool
    quoted_codes: tuple[str, ...] = ()
    rejected_codes: tuple[str, ...] = ()
