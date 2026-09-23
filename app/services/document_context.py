from contextvars import ContextVar
import re

from app.services.pdf_service import CourtDocument


_CURRENT_DOCUMENT: ContextVar[CourtDocument | None] = ContextVar(
    "current_court_document",
    default=None,
)

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
    "was", "were", "with",
}


def set_current_document(document: CourtDocument):
    return _CURRENT_DOCUMENT.set(document)


def reset_current_document(token) -> None:
    _CURRENT_DOCUMENT.reset(token)


def get_current_document() -> CourtDocument:
    document = _CURRENT_DOCUMENT.get()
    if document is None:
        raise RuntimeError("No judgment is loaded in the current agent context.")
    return document


def _tokens(value: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.'’\-]*", value.lower())
    return [word for word in words if word not in _STOP_WORDS and len(word) > 1]


def search_document(query: str, top_k: int = 5) -> list[dict]:
    document = get_current_document()
    query_terms = _tokens(query)

    if not query_terms:
        return []

    ranked = []

    for page in document.pages:
        lower = page.text.lower()

        score = sum(lower.count(term) for term in query_terms)
        if score <= 0:
            continue

        first_positions = [
            lower.find(term)
            for term in query_terms
            if lower.find(term) >= 0
        ]
        start = min(first_positions) if first_positions else 0
        snippet_start = max(0, start - 300)
        snippet_end = min(len(page.text), start + 900)

        ranked.append(
            {
                "page": page.number,
                "score": score,
                "snippet": page.text[snippet_start:snippet_end].strip(),
            }
        )

    ranked.sort(key=lambda item: (-item["score"], item["page"]))
    return ranked[: max(1, min(top_k, 10))]


def find_reference(reference: str) -> list[dict]:
    document = get_current_document()
    needle = " ".join(reference.lower().split())

    if not needle:
        return []

    matches = []

    for page in document.pages:
        normalized = " ".join(page.text.lower().split())
        position = normalized.find(needle)

        if position < 0:
            continue

        # Return the original page text around the first likely occurrence.
        lower_original = page.text.lower()
        original_position = lower_original.find(reference.lower())
        if original_position < 0:
            original_position = 0

        start = max(0, original_position - 250)
        end = min(len(page.text), original_position + len(reference) + 650)

        matches.append(
            {
                "page": page.number,
                "snippet": page.text[start:end].strip(),
            }
        )

    return matches


def page_text(page_number: int) -> str:
    document = get_current_document()

    if page_number < 1 or page_number > document.page_count:
        raise ValueError(
            f"Page {page_number} is outside the document range 1-{document.page_count}."
        )

    return document.pages[page_number - 1].text
