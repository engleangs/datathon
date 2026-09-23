from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO

from pypdf import PdfReader


@dataclass(frozen=True)
class Page:
    number: int
    text: str


@dataclass(frozen=True)
class CourtDocument:
    document_id: str
    filename: str
    source_url: str | None
    sha256: str
    pages: tuple[Page, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)


def read_pdf(
    filename: str,
    raw_bytes: bytes,
    source_url: str | None = None,
) -> CourtDocument:
    digest = sha256(raw_bytes).hexdigest()

    reader = PdfReader(BytesIO(raw_bytes))
    pages: list[Page] = []

    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(Page(number=index, text=text))

    return CourtDocument(
        document_id=digest,
        filename=filename,
        source_url=(source_url or "").strip() or None,
        sha256=digest,
        pages=tuple(pages),
    )
