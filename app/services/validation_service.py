import re

from app.schemas import CourtCaseExtraction, ValidationResult
from app.services.publication_markers import PUBLICATION_MARKERS
from app.services.pdf_service import CourtDocument


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _find_exactish(document: CourtDocument, value: str) -> bool:
    needle = _normalize(value)
    if not needle:
        return False

    return any(needle in _normalize(page.text) for page in document.pages)


def _publication_markers(document: CourtDocument) -> list[str]:
    found = []
    combined = "\n".join(page.text.lower() for page in document.pages)

    for marker in PUBLICATION_MARKERS:
        if marker in combined:
            found.append(marker)

    return found


def _evidence_items(extraction: CourtCaseExtraction):
    items = list(extraction.source_evidence)

    for legislation in extraction.legislation_cited:
        if legislation.evidence:
            items.append(legislation.evidence)

    for case in extraction.cases_cited:
        if case.evidence:
            items.append(case.evidence)

    return items


def validate_extraction(
    extraction: CourtCaseExtraction,
    document: CourtDocument,
) -> ValidationResult:
    missing: list[str] = []
    verified: list[str] = []
    reasons: list[str] = []

    if extraction.neutral_citation:
        if _find_exactish(document, extraction.neutral_citation):
            verified.append(extraction.neutral_citation)
        else:
            missing.append(extraction.neutral_citation)

    for legislation in extraction.legislation_cited:
        reference = legislation.act
        if _find_exactish(document, reference):
            verified.append(reference)
        else:
            missing.append(reference)

    for case in extraction.cases_cited:
        reference = case.citation
        if _find_exactish(document, reference):
            verified.append(reference)
        else:
            missing.append(reference)

    evidence_total = 0
    evidence_verified = 0

    for evidence in _evidence_items(extraction):
        if not evidence.text:
            continue

        evidence_total += 1

        if evidence.page and 1 <= evidence.page <= document.page_count:
            page = document.pages[evidence.page - 1]
            if _normalize(evidence.text) in _normalize(page.text):
                evidence_verified += 1
                continue

        if _find_exactish(document, evidence.text):
            evidence_verified += 1

    markers = _publication_markers(document)

    if missing:
        reasons.append(
            "One or more extracted legal references could not be matched back to the PDF."
        )

    if evidence_total == 0:
        reasons.append("No supporting evidence passage was supplied.")
    elif evidence_verified < evidence_total:
        reasons.append("One or more supporting passages could not be matched back to the PDF.")

    if markers:
        reasons.append(
            "Potential publication/suppression/confidentiality markers were detected and require human review."
        )

    if extraction.needs_human_review:
        reasons.append("The agent explicitly marked the extraction for human review.")

    status = "ACCEPTED"
    if reasons:
        status = "REVIEW_REQUIRED"

    return ValidationResult(
        status=status,
        reasons=reasons,
        missing_references=sorted(set(missing)),
        verified_references=sorted(set(verified)),
        evidence_verified=evidence_verified,
        evidence_total=evidence_total,
        publication_restriction_markers=markers,
    )
