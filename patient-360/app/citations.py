"""Citation tuples and the allergy-code guard."""

from __future__ import annotations

import re
from typing import assert_never

from app.models import Citation, CohortCitation, DocumentCitation, TableCitation

_CODE_RUN = re.compile(r"\d{6,18}")
_RISK_TABLE = "RISK_SCORE"


def digit_codes(value: str | None) -> tuple[str, ...]:
    """Return identifier-length codes, skipping compact CDA timestamps."""
    if not value:
        return ()
    found: list[str] = []
    for code in _CODE_RUN.findall(value):
        if len(code) >= 12 or code in found:
            continue
        found.append(code)
    return tuple(found)


def codes_match(left: str | None, right: str | None) -> bool:
    """True when two cells share one code."""
    left_codes = digit_codes(left)
    right_codes = digit_codes(right)
    if not left_codes or not right_codes:
        return False
    return any(code in right_codes for code in left_codes)


def conflicting_codes(csv_code: str, candidates: tuple[str | None, ...]) -> tuple[str, ...]:
    """Codes present beside the CSV code. The CSV code itself is omitted."""
    keep = set(digit_codes(csv_code))
    found: list[str] = []
    for candidate in candidates:
        for code in digit_codes(candidate):
            if code in keep or code in found:
                continue
            found.append(code)
    return tuple(found)


def format_citation(citation: Citation) -> str:
    """Render one citation as the tuple the page and the narrator must keep."""
    if isinstance(citation, DocumentCitation):
        return (
            f"(document_id={citation.document_id}, "
            f"section_loinc={citation.section_loinc}, "
            f"element_id={citation.element_id})"
        )
    if isinstance(citation, TableCitation):
        return (
            f"(table={citation.table}, patient_id={citation.patient_id}, "
            f"encounter_id={citation.encounter_id}, code={citation.code}, "
            f"start={citation.start})"
        )
    if isinstance(citation, CohortCitation):
        return (
            f"(table={citation.table}, index_date={citation.index_date}, "
            f"horizon_end={citation.horizon_end}, score={citation.score})"
        )
    assert_never(citation)


def validate_citation(citation: Citation) -> tuple[str, ...]:
    """Return problems. An element id without its document id is a problem."""
    if isinstance(citation, DocumentCitation):
        problems: list[str] = []
        if not citation.document_id.strip():
            problems.append("document_id is required because element ids restart across files")
        if not citation.section_loinc.strip():
            problems.append("section_loinc is required")
        if not citation.element_id.strip():
            problems.append("element_id is required")
        return tuple(problems)
    if isinstance(citation, TableCitation):
        if citation.table == _RISK_TABLE:
            return ("RISK_SCORE uses a cohort citation",)
        missing = [
            name
            for name, value in (
                ("table", citation.table),
                ("patient_id", citation.patient_id),
                ("encounter_id", citation.encounter_id),
                ("code", citation.code),
                ("start", citation.start),
            )
            if not value.strip()
        ]
        if missing:
            return (f"table citation missing {', '.join(missing)}",)
        return ()
    if isinstance(citation, CohortCitation):
        missing = [
            name
            for name, value in (
                ("table", citation.table),
                ("index_date", citation.index_date),
                ("horizon_end", citation.horizon_end),
                ("score", citation.score),
            )
            if not value.strip()
        ]
        if citation.table != _RISK_TABLE:
            missing.append("cohort citation table must be RISK_SCORE")
        if missing:
            return (f"cohort citation missing {', '.join(missing)}",)
        return ()
    assert_never(citation)


def rejected_code_is_guarded(text: str, quoted_code: str, rejected_code: str) -> bool:
    """A rejected code may appear only with a nearby negation and the CSV code."""
    if rejected_code not in text:
        return True
    if quoted_code not in text:
        return False
    for match in re.finditer(re.escape(rejected_code), text):
        window = text[max(0, match.start() - 80) : match.start()].lower()
        if "not" not in window:
            return False
    return True
