from app.schemas import (
    CourtCaseExtraction,
    EvidenceSnippet,
    LegislationReference,
)
from app.services.pdf_service import CourtDocument, Page
from app.services.validation_service import validate_extraction


def test_accepted_when_references_and_evidence_match():
    document = CourtDocument(
        document_id="abc",
        filename="sample.pdf",
        source_url=None,
        sha256="abc",
        pages=(
            Page(
                1,
                "IN THE HIGH COURT OF NEW ZEALAND\n"
                "[2026] NZHC 123\n"
                "The Employment Relations Act 2000 applies.",
            ),
        ),
    )

    extraction = CourtCaseExtraction(
        case_name="Example v Example",
        neutral_citation="[2026] NZHC 123",
        court="High Court",
        source_document="sample.pdf",
        legislation_cited=[
            LegislationReference(
                act="Employment Relations Act 2000",
                evidence=EvidenceSnippet(
                    page=1,
                    text="The Employment Relations Act 2000 applies.",
                ),
            )
        ],
    )

    result = validate_extraction(extraction, document)

    assert result.status == "ACCEPTED"
    assert not result.missing_references
    assert result.evidence_verified == 1
