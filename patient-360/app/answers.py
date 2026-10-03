"""Build cited answers from rows the caller already retrieved."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.citations import (
    codes_match,
    conflicting_codes,
    format_citation,
    rejected_code_is_guarded,
    validate_citation,
)
from app.guardrails import has_banned_clinical_claim, refuse
from app.models import (
    Answer,
    AnswerStatus,
    Citation,
    CohortCitation,
    DocumentCitation,
    Intent,
    TableCitation,
)
from app.rows import normalize_row

_MEDICATION_TABLE = "MEDICATION"
_ALLERGY_TABLE = "ALLERGY"
_RISK_TABLE = "RISK_SCORE"


def answer_medication(
    medication_rows: Sequence[Mapping[str, object]],
    section_rows: Sequence[Mapping[str, object]],
    patient_rows: Sequence[Mapping[str, object]] = (),
) -> Answer:
    """Cite one antihistamine row, plus C-CDA cells that carry the same code."""
    medications = [normalize_row(row) for row in medication_rows]
    if len(medications) == 0:
        return refuse(
            Intent.MEDICATION_CITATION,
            "Refused. No medication row matched this question, so there is no citation tuple.",
        )
    if len(medications) != 1:
        return refuse(
            Intent.MEDICATION_CITATION,
            "Refused. Retrieval returned "
            f"{len(medications)} medication rows. This demo cites one row and does not choose among them.",
        )
    medication = medications[0]
    table_citation = _table_citation(_MEDICATION_TABLE, medication)
    if table_citation is None or not medication.get("description"):
        return refuse(
            Intent.MEDICATION_CITATION,
            "Refused. The medication row is missing patient, encounter, code, or start.",
        )
    sections = _matching_documents(section_rows, medication["code"] or "", medication["patient_id"])
    citations: list[Citation] = [table_citation, *[document for _, document in sections]]
    name = _patient_label(patient_rows)
    prefix = f"{name}: " if name else ""
    lines = [
        f"{prefix}{medication['description']} is on the retrieved medication list.",
        f"Code {medication['code']}. Start {medication['start']}.",
        format_citation(table_citation) + ".",
    ]
    if sections:
        for section, document in sections:
            lines.append(format_citation(document) + ".")
            if section.get("text"):
                lines.append(f"Section text: {section['text']}.")
    else:
        lines.append(
            "No document-section row matched that code, so this answer does not claim a C-CDA cell."
        )
    lines.append("Synthetic Synthea record. Not for care.")
    return _cited(
        Intent.MEDICATION_CITATION,
        " ".join(lines),
        tuple(citations),
        quoted_codes=(medication["code"] or "",),
    )


def answer_allergy(
    allergy_rows: Sequence[Mapping[str, object]],
    section_rows: Sequence[Mapping[str, object]],
) -> Answer:
    """Quote the allergies.csv code. A different code in the same entry stays unquoted."""
    allergies = [normalize_row(row) for row in allergy_rows]
    if len(allergies) == 0:
        return refuse(
            Intent.ALLERGY_CITATION,
            "Refused. No allergy row matched this question, so there is no citation tuple.",
        )
    if len(allergies) != 1:
        return refuse(
            Intent.ALLERGY_CITATION,
            "Refused. Retrieval returned "
            f"{len(allergies)} allergy rows. This demo cites one row and does not choose among them.",
        )
    allergy = allergies[0]
    table_citation = _table_citation(_ALLERGY_TABLE, allergy)
    if table_citation is None or not allergy.get("code"):
        return refuse(
            Intent.ALLERGY_CITATION,
            "Refused. The allergy row is missing patient, encounter, code, or start.",
        )
    csv_code = allergy["code"] or ""
    documents = _matching_documents(section_rows, csv_code, allergy["patient_id"])
    rejected = conflicting_codes(
        csv_code,
        tuple(
            value
            for row in section_rows
            for value in (
                normalize_row(row).get("code"),
                normalize_row(row).get("text"),
            )
        ),
    )
    citations: list[Citation] = [table_citation, *[document for _, document in documents]]
    lines = [
        f"Quoted allergy code {csv_code}, {allergy.get('description') or 'description not on the row'}.",
        f"Start {allergy['start']}. Encounter {allergy['encounter_id']}.",
        "The quoted code is the allergies.csv code on the retrieved row.",
        format_citation(table_citation) + ".",
    ]
    for section, document in documents:
        lines.append(format_citation(document) + ".")
        if section.get("text"):
            lines.append(f"Section text: {section['text']}.")
    for code in rejected:
        lines.append(
            f"Not the quoted allergy: retrieved code {code} differs from allergies.csv code {csv_code}."
        )
    if not documents:
        lines.append(
            "No document-section row matched the allergies.csv code, so this answer does not claim a C-CDA cell."
        )
    lines.append("Synthetic Synthea record. Not for care.")
    text = " ".join(lines)
    for code in rejected:
        if not rejected_code_is_guarded(text, csv_code, code):
            return refuse(
                Intent.ALLERGY_CITATION,
                "Refused. The allergy guard stopped an answer that would quote a code other than allergies.csv.",
            )
    return _cited(
        Intent.ALLERGY_CITATION,
        text,
        tuple(citations),
        quoted_codes=(csv_code,),
        rejected_codes=rejected,
    )


def answer_risk(risk_rows: Sequence[Mapping[str, object]]) -> Answer:
    """Describe CORE.RISK_SCORE. Counts and rates come from the rows."""
    rows = [normalize_row(row) for row in risk_rows]
    if not rows:
        return refuse(
            Intent.RISK_COHORT,
            "Refused. CORE.RISK_SCORE returned no rows, so the point count is not shown.",
        )
    try:
        scores = [_RiskBucket.from_row(row) for row in rows]
    except ValueError as exc:
        return refuse(Intent.RISK_COHORT, f"Refused. {exc}")
    score_keys = [bucket.score for bucket in scores]
    if len(score_keys) != len(set(score_keys)):
        return refuse(
            Intent.RISK_COHORT,
            "Refused. CORE.RISK_SCORE repeated a score, so this page will not pick a row.",
        )
    if _disagree(rows, "cohort_n") or _disagree(rows, "event_n") or _disagree(rows, "base_rate"):
        return refuse(
            Intent.RISK_COHORT,
            "Refused. CORE.RISK_SCORE rows disagree on the cohort, the events, or the base rate.",
        )
    if _disagree(rows, "index_date") or _disagree(rows, "horizon_end"):
        return refuse(
            Intent.RISK_COHORT,
            "Refused. CORE.RISK_SCORE rows disagree on the index or the horizon.",
        )
    first = scores[0]
    lines = [
        f"CORE.RISK_SCORE returned a point count for index {first.index_date} through {first.horizon_end}.",
        f"Cohort size {first.cohort_n}. Events {first.event_n}. Base rate {first.base_rate_text}.",
        "This is a point count, not a validated stratifier, not a probability of deterioration, "
        "and not a care recommendation.",
    ]
    citations: list[Citation] = []
    by_score: dict[int, _RiskBucket] = {}
    for bucket in sorted(scores, key=lambda item: item.score):
        by_score[bucket.score] = bucket
        if bucket.event_rate_text is None:
            lines.append(
                f"Score {bucket.score}: {bucket.patient_count} patients. "
                "The retrieved row has no event rate."
            )
        else:
            lines.append(
                f"Score {bucket.score}: {bucket.patient_count} patients, "
                f"event rate {bucket.event_rate_text}."
            )
        citations.append(
            CohortCitation(
                table=_RISK_TABLE,
                index_date=bucket.index_date,
                horizon_end=bucket.horizon_end,
                score=str(bucket.score),
            )
        )
    if 1 in by_score and 2 in by_score:
        rate_1 = by_score[1].event_rate
        rate_2 = by_score[2].event_rate
        if rate_1 is not None and rate_2 is not None and rate_2 < rate_1:
            lines.append("Score 2 sits below score 1 on the retrieved rates.")
    try:
        ge2_count = _optional_agreement(rows, "ge2_patient_count")
        ge2_rate = _optional_agreement(rows, "ge2_event_rate")
        excluded_dead = _optional_agreement(rows, "excluded_dead")
        excluded_born = _optional_agreement(rows, "excluded_born")
    except ValueError as exc:
        return refuse(Intent.RISK_COHORT, f"Refused. {exc}")
    if ge2_count is not None and ge2_rate is not None:
        try:
            lines.append(
                f"Score 2 or higher: {format_count(ge2_count)} patients, "
                f"event rate {format_rate(ge2_rate)}, as returned on the risk rows."
            )
        except ValueError as exc:
            return refuse(Intent.RISK_COHORT, f"Refused. {exc}")
    if excluded_dead is not None and excluded_born is not None:
        try:
            lines.append(
                "Excluded before the cohort, as returned on the risk rows: "
                f"dead on or before the index {format_count(excluded_dead)}; "
                f"born on or after the index {format_count(excluded_born)}."
            )
        except ValueError as exc:
            return refuse(Intent.RISK_COHORT, f"Refused. {exc}")
    lines.append(
        "This page does not read C-CDA text for the point count, and it does not retune the four points."
    )
    text = " ".join(lines)
    if has_banned_clinical_claim(text):
        return refuse(
            Intent.RISK_COHORT,
            "Refused. The risk wording failed the clinical-claim check, so the panel is not shown.",
        )
    return _cited(Intent.RISK_COHORT, text, tuple(citations))


def format_rate(value: str) -> str:
    """Format a fraction stored by CORE.RISK_SCORE as a percent."""
    number = float(value)
    if number < 0 or number > 1:
        raise ValueError("event rate must be a fraction from 0 through 1")
    return f"{number * 100:.2f}%"


def format_count(value: str) -> str:
    """Format a whole-number count from a warehouse cell."""
    number = float(value)
    if not number.is_integer():
        raise ValueError("count must be a whole number")
    return str(int(number))


class _RiskBucket:
    """One score row after its numbers have parsed."""

    def __init__(
        self,
        score: int,
        patient_count: str,
        event_rate: float | None,
        event_rate_text: str | None,
        cohort_n: str,
        event_n: str,
        base_rate_text: str,
        index_date: str,
        horizon_end: str,
    ) -> None:
        self.score = score
        self.patient_count = patient_count
        self.event_rate = event_rate
        self.event_rate_text = event_rate_text
        self.cohort_n = cohort_n
        self.event_n = event_n
        self.base_rate_text = base_rate_text
        self.index_date = index_date
        self.horizon_end = horizon_end

    @classmethod
    def from_row(cls, row: dict[str, str | None]) -> _RiskBucket:
        required = (
            "score",
            "patient_count",
            "cohort_n",
            "event_n",
            "base_rate",
            "index_date",
            "horizon_end",
        )
        if any(not row.get(name) for name in required):
            raise ValueError("CORE.RISK_SCORE is missing a cohort, event, rate, index, or score field.")
        patient_count = format_count(row["patient_count"] or "")
        event_rate_text: str | None
        event_rate: float | None
        if row.get("event_rate") is None:
            if patient_count != "0":
                raise ValueError("CORE.RISK_SCORE has patients and no event rate.")
            event_rate = None
            event_rate_text = None
        else:
            event_rate = float(row["event_rate"] or "")
            event_rate_text = format_rate(row["event_rate"] or "")
        return cls(
            score=int(format_count(row["score"] or "")),
            patient_count=patient_count,
            event_rate=event_rate,
            event_rate_text=event_rate_text,
            cohort_n=format_count(row["cohort_n"] or ""),
            event_n=format_count(row["event_n"] or ""),
            base_rate_text=format_rate(row["base_rate"] or ""),
            index_date=row["index_date"] or "",
            horizon_end=row["horizon_end"] or "",
        )


def _table_citation(table: str, row: dict[str, str | None]) -> TableCitation | None:
    patient_id = row.get("patient_id")
    encounter_id = row.get("encounter_id")
    code = row.get("code")
    start = row.get("start")
    if not patient_id or not encounter_id or not code or not start:
        return None
    return TableCitation(
        table=table,
        patient_id=patient_id,
        encounter_id=encounter_id,
        code=code,
        start=start,
    )


def _matching_documents(
    section_rows: Sequence[Mapping[str, object]],
    csv_code: str,
    patient_id: str | None,
) -> list[tuple[dict[str, str | None], DocumentCitation]]:
    matched: list[tuple[dict[str, str | None], DocumentCitation]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in section_rows:
        section = normalize_row(raw)
        if patient_id and section.get("patient_id") not in {None, patient_id}:
            continue
        haystack = " ".join(
            part for part in (section.get("code"), section.get("text")) if part
        )
        if not codes_match(haystack, csv_code):
            continue
        document_id = section.get("document_id")
        section_loinc = section.get("section_loinc")
        element_id = section.get("element_id")
        if not document_id or not section_loinc or not element_id:
            continue
        citation = DocumentCitation(
            document_id=document_id,
            section_loinc=section_loinc,
            element_id=element_id,
        )
        if validate_citation(citation):
            continue
        key = citation.as_tuple()
        if key in seen:
            continue
        seen.add(key)
        matched.append((section, citation))
    return matched


def _patient_label(patient_rows: Sequence[Mapping[str, object]]) -> str | None:
    if len(patient_rows) != 1:
        return None
    patient = normalize_row(patient_rows[0])
    first = patient.get("first_name")
    last = patient.get("last_name")
    if not first or not last:
        return None
    return f"{first} {last}"


def _disagree(rows: Sequence[dict[str, str | None]], key: str) -> bool:
    values = {row.get(key) for row in rows}
    return len(values) != 1 or None in values


def _optional_agreement(rows: Sequence[dict[str, str | None]], key: str) -> str | None:
    values = {row.get(key) for row in rows}
    if values == {None}:
        return None
    if len(values) != 1 or None in values:
        raise ValueError(f"CORE.RISK_SCORE rows disagree on {key}.")
    return next(iter(values))


def _cited(
    intent: Intent,
    text: str,
    citations: tuple[Citation, ...],
    quoted_codes: tuple[str, ...] = (),
    rejected_codes: tuple[str, ...] = (),
) -> Answer:
    answer = Answer(
        status=AnswerStatus.CITED,
        intent=intent,
        text=text,
        citations=citations,
        narration_allowed=True,
        quoted_codes=quoted_codes,
        rejected_codes=rejected_codes,
    )
    problems: list[str] = []
    if not citations:
        problems.append("a cited answer needs a citation tuple")
    for citation in citations:
        problems.extend(validate_citation(citation))
    if has_banned_clinical_claim(text):
        problems.append("banned clinical claim")
    if problems:
        return refuse(
            intent,
            "Refused. The citation check failed, so this answer is not shown.",
        )
    return answer
