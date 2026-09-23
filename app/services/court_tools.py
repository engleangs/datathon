import json

from strands import tool

from app.services.document_context import (
    find_reference,
    get_current_document,
    page_text,
    search_document,
)
from app.services.publication_markers import PUBLICATION_MARKERS


@tool
def search_judgment(query: str, top_k: int = 5) -> str:
    """Search the loaded court judgment and return the best matching pages and snippets."""
    return json.dumps(search_document(query, top_k=top_k), ensure_ascii=False)


@tool
def get_page(page_number: int) -> str:
    """Read a specific 1-based page from the currently loaded court judgment."""
    return page_text(page_number)


@tool
def validate_reference(reference: str) -> str:
    """Verify whether a legal citation, Act name, case citation, or exact phrase exists in the loaded judgment."""
    matches = find_reference(reference)
    return json.dumps(
        {
            "reference": reference,
            "found": bool(matches),
            "matches": matches[:5],
        },
        ensure_ascii=False,
    )


@tool
def scan_publication_restriction_markers() -> str:
    """Scan the loaded judgment for textual markers that may indicate publication, suppression, confidentiality, or anonymisation restrictions. This is a flagging tool, not a legal determination."""
    document = get_current_document()
    found = []

    for marker in PUBLICATION_MARKERS:
        pages = []
        for page in document.pages:
            if marker in page.text.lower():
                pages.append(page.number)

        if pages:
            found.append({"marker": marker, "pages": pages[:10]})

    return json.dumps(found, ensure_ascii=False)
