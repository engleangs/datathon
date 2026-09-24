import json

from app.schemas import CourtCaseExtraction
from app.services.debug_service import save_debug_extraction
from app.services.pdf_service import CourtDocument, Page


def test_save_debug_extraction_writes_json_with_safe_filename(tmp_path):
    document = CourtDocument(
        document_id="abc123",
        filename="Example judgment (final).pdf",
        source_url=None,
        sha256="abc123def456789",
        pages=(Page(number=1, text="Example"),),
    )
    extraction = CourtCaseExtraction(
        case_name="Example v Example",
        source_document=document.filename,
    )

    output_path = save_debug_extraction(extraction, document, tmp_path)

    assert output_path.name == "Example-judgment-final-abc123def456.json"
    assert json.loads(output_path.read_text(encoding="utf-8"))["case_name"] == "Example v Example"
