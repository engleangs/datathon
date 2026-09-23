"""Text extraction and rule-based fields for District Court of New Zealand decisions.

No OCR. The PDF must have a text layer (born-digital). Scanned pages are
detected and flagged, not read.

Youth Court and Family Court decisions are detected and EXCLUDED: no fields
are extracted and the text is dropped, because those decisions have strict
publication rules.

Kept separate from the Streamlit UI so it can be unit-tested and reused.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MIN_CHARS_PER_PAGE = 40          # below this, a page counts as "no text layer"
REFORM_DATE = date(2025, 6, 29)  # Sentencing (Reform) Amendment Act 2025 in force
MITIGATION_CAP_PCT = 40

MONTHS = ("January|February|March|April|May|June|July|August|"
          "September|October|November|December")
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty-one": 21, "twenty-two": 22, "twenty-three": 23,
    "twenty-four": 24, "thirty": 30, "thirty-six": 36, "forty-eight": 48,
}
NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
DURATION = (rf"(?:{NUM}\s+years?(?:,?\s*(?:and\s+)?{NUM}\s+months?)?"
            rf"|{NUM}\s+months?(?:\s+and\s+{NUM}\s+weeks?)?|{NUM}\s+weeks?)")

RE_CITATION = re.compile(r"\[(\d{4})\]\s*(NZ[A-Za-z]{2,6})\s*(\d{1,6})")
RE_DC_HEADER = re.compile(r"IN THE DISTRICT COURT\s*(?:\n|\s)+AT\s+([A-Z][A-Z' -]+?)\s*(?:\n|$)")
RE_EXCLUDED_HEADER = re.compile(r"IN THE (YOUTH COURT|FAMILY COURT)", re.IGNORECASE)
RE_FILE_NO = re.compile(r"\b((?:CRI|CIV|CIR)-\d{4}-\d{3}-\d{1,6})\b")
RE_DATE_LABEL = r"(?:\d{1,2}(?:\s*(?:and|&|,|-)\s*\d{1,2})*\s+)?(\d{1,2}\s+(?:%s)\s+\d{4})" % MONTHS
RE_JUDGMENT_DATE = re.compile(r"(?:Judgment|Sentence|Decision)(?:\s+Date)?\s*:\s*" + RE_DATE_LABEL, re.IGNORECASE)
RE_HEARING_DATE = re.compile(r"Hearing(?:\s+Date)?s?\s*:\s*" + RE_DATE_LABEL, re.IGNORECASE)
RE_JUDGE = re.compile(
    r"(?:NOTES|JUDGMENT|DECISION|REASONS|RULING)\s+OF\s+(?:DISTRICT\s+COURT\s+)?JUDGE\s+"
    r"([A-Z][A-Z.' -]+?)\s*(?:\[|ON\b|AS\b|\n|$)"
)
RE_DOCTYPE = [
    ("sentencing", re.compile(r"ON\s+SENTENCING|SENTENCING\s+NOTES|NOTES\s+OF\s+JUDGE", re.I)),
    ("reserved judgment", re.compile(r"RESERVED\s+(?:JUDGMENT|DECISION)", re.I)),
    ("oral judgment", re.compile(r"ORAL\s+JUDGMENT", re.I)),
    ("appeal", re.compile(r"\bON\s+APPEAL\b|APPEAL\s+FROM\s+(?:A\s+)?DECISION", re.I)),
]
RE_PUBLICATION = re.compile(
    r"^\s*((?:EDITORIAL\s+)?NOTE\s*:.*?)(?:\n\s*\n|IN THE DISTRICT COURT)", re.I | re.S | re.M
)
RE_SUPPRESSION = re.compile(r"suppress|prohibit(?:ed|ing|s)? (?:by|publication)|non-publication", re.I)
RE_STATUTE = re.compile(r"\b((?:[A-Z][a-zA-Z'()]+\s){1,8}(?:Act|Regulations|Rules)\s(?:1[89]\d{2}|20\d{2}))\b")
RE_SECTION = re.compile(
    r"\bss?\s?(\d+[A-Z]?(?:\(\d+[A-Za-z]?\))*(?:\([a-z]+\))?)\s+(?:of\s+the\s+)?"
    r"((?:[A-Z][a-zA-Z'()]+\s){1,6}Act\s(?:1[89]\d{2}|20\d{2}))"
)
RE_STARTING_POINT = re.compile(rf"starting\s+point\s+(?:of|at)\s+(?:about\s+|around\s+)?({DURATION})", re.I)
RE_END_SENTENCE = re.compile(
    rf"(?:end\s+sentence|final\s+sentence|sentence\s+you\s+to|you\s+are\s+sentenced\s+to|"
    rf"sentenced\s+to|resulting\s+sentence)\s+(?:is\s+|of\s+)?({DURATION})", re.I)
RE_PLEA_PCT = [
    re.compile(r"(\d{1,2})\s?(?:per\s?cent|%)[^.]{0,60}?guilty\s+pleas?", re.I),
    re.compile(r"guilty\s+pleas?[^.]{0,80}?(\d{1,2})\s?(?:per\s?cent|%)", re.I),
]
RE_MITIGATION_PCT = re.compile(
    r"(\d{1,2})\s?(?:per\s?cent|%)[^.]{0,80}?(remorse|youth|s\s?27|cultural|rehabilitat|"
    r"good\s+character|addiction|mental\s+health|background)", re.I)
RE_HOME_DETENTION = re.compile(
    rf"(?:commute|convert|substitute|impose)[^.]{{0,60}}?({DURATION})'?\s+home\s+detention", re.I)
RE_CLAIM = re.compile(r"claim(?:s|ed)?\s+(?:is\s+)?(?:for\s+|of\s+)?\$\s?([\d,]+(?:\.\d{2})?)", re.I)
RE_AWARD = re.compile(
    r"judgment\s+(?:is\s+)?(?:entered\s+)?for\s+the\s+(?:plaintiff|applicant|appellant)[^.$]{0,40}\$\s?([\d,]+(?:\.\d{2})?)",
    re.I)
RE_REPARATION = re.compile(r"reparation[^.$]{0,60}\$\s?([\d,]+(?:\.\d{2})?)", re.I)
SENTENCE_TYPES = [
    ("home detention", r"home\s+detention"),
    ("community detention", r"community\s+detention"),
    ("intensive supervision", r"intensive\s+supervision"),
    ("imprisonment", r"imprisonment"),
    ("supervision", r"\bsupervision\b"),
    ("community work", r"community\s+work"),
    ("discharge without conviction", r"discharged?\s+without\s+conviction"),
    ("conviction and discharge", r"convicted\s+and\s+discharged"),
    ("fine", r"\bfined?\b"),
]


@dataclass
class DcResult:
    file_name: str
    sha256: str
    size_bytes: int
    page_count: int = 0
    text_pages: int = 0
    total_chars: int = 0
    needs_ocr: bool = False
    partly_scanned: bool = False
    excluded_reason: str | None = None   # youth_court / family_court / not_district_court
    error: str | None = None
    pages: list[str] = field(default_factory=list, repr=False)

    # Header fields
    neutral_citation: str | None = None
    registry: str | None = None
    file_number: str | None = None
    case_type: str | None = None         # criminal / civil
    judge: str | None = None
    judgment_date: str | None = None
    hearing_date: str | None = None
    document_type: str | None = None
    publication_note: str | None = None
    mentions_suppression: bool = False

    # Sentencing fields (criminal)
    starting_point: str | None = None
    starting_point_months: float | None = None
    end_sentence: str | None = None
    end_sentence_months: float | None = None
    sentence_type: str | None = None
    home_detention_months: float | None = None
    guilty_plea_pct: float | None = None
    personal_mitigation_pct: float | None = None
    reparation_nzd: float | None = None
    reform_period: str | None = None

    # Civil fields
    amount_claimed_nzd: float | None = None
    amount_awarded_nzd: float | None = None

    statutes_cited: list[str] = field(default_factory=list)
    sections_cited: list[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n\n".join(self.pages)

    @property
    def is_usable(self) -> bool:
        return not self.error and not self.needs_ocr and not self.excluded_reason

    def summary_row(self) -> dict:
        d = asdict(self)
        d.pop("pages")
        d["statutes_cited"] = "; ".join(self.statutes_cited)
        d["sections_cited"] = "; ".join(self.sections_cited)
        return d


# ---------------------------------------------------------------- helpers
def _clean(text: str) -> str:
    text = text.replace("\u00a0", " ").replace("\u2019", "'").replace("\u2013", "-")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _num(token: str | None) -> float | None:
    if not token:
        return None
    token = token.lower().strip()
    if token in NUMBER_WORDS:
        return float(NUMBER_WORDS[token])
    try:
        return float(token)
    except ValueError:
        return None


def duration_to_months(text: str | None) -> float | None:
    """'2 years and 6 months' -> 30.0, 'eighteen months' -> 18.0, '6 weeks' -> 1.5."""
    if not text:
        return None
    t = text.lower()
    total, found = 0.0, False
    for unit, factor in (("year", 12.0), ("month", 1.0), ("week", 0.25)):
        m = re.search(rf"{NUM}\s+{unit}s?", t)
        if m and _num(m.group(1)) is not None:
            total += _num(m.group(1)) * factor
            found = True
    return round(total, 2) if found else None


def _unique(items, limit: int | None = None) -> list[str]:
    seen, out = set(), []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
        if limit and len(out) >= limit:
            break
    return out


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d %B %Y").date()
    except ValueError:
        return None


# ---------------------------------------------------------------- main API
def read_pdf(data: bytes, file_name: str) -> DcResult:
    """Read the text layer of every page. Never runs OCR."""
    res = DcResult(file_name=file_name, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data))

    if not data.startswith(b"%PDF-"):
        res.error = "Not a PDF file (missing %PDF- header)."
        return res
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                res.error = "PDF is password-protected."
                return res
        for page in reader.pages:
            try:
                res.pages.append(_clean(page.extract_text() or ""))
            except Exception:
                res.pages.append("")
    except PdfReadError as exc:
        res.error = f"Could not read PDF: {exc}"
        return res

    res.page_count = len(res.pages)
    res.text_pages = sum(len(p) >= MIN_CHARS_PER_PAGE for p in res.pages)
    res.total_chars = sum(len(p) for p in res.pages)
    res.needs_ocr = res.page_count > 0 and res.text_pages == 0
    res.partly_scanned = 0 < res.text_pages < res.page_count

    if res.needs_ocr:
        return res

    _gate(res)
    if res.excluded_reason:
        res.pages = []          # drop the text: excluded decisions are not kept
        return res

    extract_fields(res)
    return res


def _gate(res: DcResult) -> None:
    """Exclusion gate. Runs before any field extraction."""
    head = "\n".join(res.pages[:2])
    m = RE_CITATION.search(head)
    code = m.group(2).upper() if m else None
    hdr = RE_EXCLUDED_HEADER.search(head)
    if code == "NZYC" or (hdr and hdr.group(1).upper() == "YOUTH COURT"):
        res.excluded_reason = "youth_court"
    elif code == "NZFC" or (hdr and hdr.group(1).upper() == "FAMILY COURT"):
        res.excluded_reason = "family_court"
    elif code and code != "NZDC":
        res.excluded_reason = "not_district_court"
    if m:
        res.neutral_citation = f"[{m.group(1)}] {m.group(2)} {m.group(3)}"


def extract_fields(res: DcResult) -> None:
    """Header fields come from the first 2 pages. Sentencing fields come from
    the whole text, preferring the LAST match (the judge's final calculation)."""
    head = "\n".join(res.pages[:2])
    body = res.full_text

    m = RE_DC_HEADER.search(head)
    if m:
        res.registry = m.group(1).strip().title()

    m = RE_FILE_NO.search(head)
    if m:
        res.file_number = m.group(1)
        res.case_type = "civil" if m.group(1).startswith("CIV") else "criminal"

    m = RE_JUDGE.search(head)
    if m:
        res.judge = "Judge " + " ".join(w.capitalize() if len(w) > 2 else w for w in m.group(1).split())

    m = RE_JUDGMENT_DATE.search(head)
    if m:
        res.judgment_date = m.group(1)
    m = RE_HEARING_DATE.search(head)
    if m:
        res.hearing_date = m.group(1)

    for label, rx in RE_DOCTYPE:
        if rx.search(head):
            res.document_type = label
            break

    m = RE_PUBLICATION.search(res.pages[0] if res.pages else "")
    if m:
        res.publication_note = re.sub(r"\s+", " ", m.group(1)).strip()[:500]
    res.mentions_suppression = bool(res.publication_note) or bool(RE_SUPPRESSION.search(head))

    # ---- sentencing
    if res.case_type != "civil":
        sps = RE_STARTING_POINT.findall(body)
        if sps:
            res.starting_point = sps[0][0] if isinstance(sps[0], tuple) else sps[0]
            res.starting_point_months = duration_to_months(res.starting_point)
        ends = [mm.group(1) for mm in RE_END_SENTENCE.finditer(body)]
        if ends:
            res.end_sentence = ends[-1]
            res.end_sentence_months = duration_to_months(res.end_sentence)

        tail = "\n".join(res.pages[-2:])
        for label, pattern in SENTENCE_TYPES:
            if re.search(pattern, tail, re.I):
                res.sentence_type = label
                break

        for rx in RE_PLEA_PCT:
            m = rx.search(body)
            if m:
                res.guilty_plea_pct = float(m.group(1))
                break

        mit = [float(mm.group(1)) for mm in RE_MITIGATION_PCT.finditer(body)]
        res.personal_mitigation_pct = sum(mit) if mit else None

        reps = [float(mm.group(1).replace(",", "")) for mm in RE_REPARATION.finditer(body)]
        res.reparation_nzd = max(reps) if reps else None

        hd = [mm.group(1) for mm in RE_HOME_DETENTION.finditer(body)]
        if hd:
            res.home_detention_months = duration_to_months(hd[-1])
            res.sentence_type = "home detention"

        if res.case_type is None and (res.starting_point or res.end_sentence):
            res.case_type = "criminal"

    # ---- civil
    if res.case_type == "civil":
        m = RE_CLAIM.search(body)
        if m:
            res.amount_claimed_nzd = float(m.group(1).replace(",", ""))
        awards = [float(mm.group(1).replace(",", "")) for mm in RE_AWARD.finditer(body)]
        res.amount_awarded_nzd = awards[-1] if awards else None

    d = _parse_date(res.judgment_date)
    if d:
        res.reform_period = "after reform" if d >= REFORM_DATE else "before reform"

    res.statutes_cited = _unique(
        re.sub(r"^(?:The|the|Under|under|In|in|Of|of|And|and|Section|section)\s+", "", s)
        for s in RE_STATUTE.findall(body)
    )
    res.sections_cited = _unique((f"s {sec} {act.strip()}" for sec, act in RE_SECTION.findall(body)), limit=20)
