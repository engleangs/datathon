from app.services.document_context import (
    find_reference,
    reset_current_document,
    search_document,
    set_current_document,
)
from app.services.pdf_service import CourtDocument, Page


def sample_document():
    return CourtDocument(
        document_id="abc",
        filename="sample.pdf",
        source_url=None,
        sha256="abc",
        pages=(
            Page(
                1,
                "IN THE HIGH COURT OF NEW ZEALAND\n[2026] NZHC 123\n"
                "The Employment Relations Act 2000 is relevant.",
            ),
            Page(
                2,
                "The application is dismissed. The Court considered section 103.",
            ),
        ),
    )


def test_search_document():
    token = set_current_document(sample_document())

    try:
        results = search_document("Employment Relations Act")
        assert results
        assert results[0]["page"] == 1
    finally:
        reset_current_document(token)


def test_validate_reference():
    token = set_current_document(sample_document())

    try:
        matches = find_reference("Employment Relations Act 2000")
        assert matches
        assert matches[0]["page"] == 1
    finally:
        reset_current_document(token)
