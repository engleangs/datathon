"""Rule-based field extraction for New Zealand District Court PDFs.

No API calls. Every field comes from regular expressions on the PDF text layer.
Each sentencing field also returns an "evidence" snippet so a person can check it.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime

import pdfplumber



# Text helpers

MONTHS = ("january february march april may june july august september "
          "october november december").split()
DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")\s*,?\s+(\d{4})\b",
    re.I)
NUM_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

WORD_NUMS = {
    "zero": 0, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60,
}
NUM_WORD = (r"(?:\d+(?:\.\d+)?|(?:twenty|thirty|forty|fifty|sixty)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?"
            r"|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
            r"|one|two|three|four|five|six|seven|eight|nine|ten|an?)")


def word_to_num(tok: str) -> float | None:
    tok = tok.lower().strip()
    try:
        return float(tok)
    except ValueError:
        pass
    parts = re.split(r"[\s-]+", tok)
    total = 0
    for p in parts:
        if p not in WORD_NUMS:
            return None
        total += WORD_NUMS[p]
    return float(total)


def clean(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace(" ", " ")
    text = text.replace("–", "-").replace("—", "-")
    return text


def flat(text: str) -> str:
    """One line, single spaces. Good for phrase matching across line breaks."""
    return re.sub(r"\s+", " ", text)


def to_iso(day: str, month: str, year: str) -> str | None:
    try:
        m = MONTHS.index(month.lower()) + 1
        return datetime(int(year), m, int(day)).strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def snippet(text: str, start: int, end: int, pad: int = 90) -> str:
    return "..." + text[max(0, start - pad): end + pad].strip() + "..."



# Durations

# "two years and three months", "2 years, 6 months", "18 months", "three years"
DURATION_RE = re.compile(
    rf"(?:(?P<y>{NUM_WORD})\s+years?)?"
    rf"(?:\s*(?:,|and)?\s*(?P<m>{NUM_WORD})\s+months?)?"
    rf"(?:\s*(?:,|and)?\s*(?P<w>{NUM_WORD})\s+weeks?)?",
    re.I)


def parse_duration(s: str) -> tuple[float | None, int, int]:
    """Return (months, start, end) for the first duration in s."""
    for m in DURATION_RE.finditer(s):
        if not (m.group("y") or m.group("m") or m.group("w")):
            continue
        y = word_to_num(m.group("y")) if m.group("y") else 0
        mo = word_to_num(m.group("m")) if m.group("m") else 0
        w = word_to_num(m.group("w")) if m.group("w") else 0
        if y is None or mo is None or w is None:
            continue
        months = y * 12 + mo + round(w / 4.345, 1)
        return months, m.start(), m.end()
    return None, -1, -1



# Header fields

CITATION_RE = re.compile(r"\[(\d{4})\]\s*(NZ[A-Za-z]{2,5})\s*(\d+)")
COURT_RE = re.compile(
    r"IN THE (DISTRICT COURT|YOUTH COURT|FAMILY COURT|HIGH COURT|COURT OF APPEAL|SUPREME COURT"
    r"|ENVIRONMENT COURT|EMPLOYMENT COURT)", re.I)
FILE_NO_RE = re.compile(r"\b(CRI|CIV|FAM|CIR)-(\d{4})-(\d{3})-(\d{4,6})\b")
REGISTRY_RE = re.compile(
    r"IN THE (DISTRICT|YOUTH|FAMILY) COURT\s*(?:\n\s*)?AT\s+([A-Z][A-Z .'\-]+?)\s*(?:\n|$|I TE)",
    re.I)

DATE_LABELS = [
    "Judgment", "Sentence", "Sentenced", "Sentencing", "Decision",
    "Date of Decision", "Date of Judgment", "Ruling", "Minute",
]
DATE_LABEL_RE = re.compile(
    r"^\s*(?:" + "|".join(DATE_LABELS) + r")\s*(?:date)?\s*:\s*(.+)$",
    re.I | re.M)

# (pattern, label). Order matters: first match wins.
DOC_TYPES = [
    (r"NOTES OF JUDGE .{0,80}?ON SENTENCING", "Sentencing notes"),
    (r"SENTENCING NOTES", "Sentencing notes"),
    (r"NOTES OF JUDGE .{0,80}?ON (?:DISPOSITION|RESENTENCING)", "Sentencing notes"),
    (r"RESERVED SENTENCING DECISION", "Sentencing decision"),
    (r"SENTENCING DECISION", "Sentencing decision"),
    (r"RESERVED JUDGMENT", "Reserved judgment"),
    (r"RESERVED DECISION", "Reserved decision"),
    (r"ORAL JUDGMENT", "Oral judgment"),
    (r"(?:NOTES OF )?JUDGMENT OF (?:JUDGE|THE COURT)", "Judgment"),
    (r"DECISION OF JUDGE", "Decision"),
    (r"RULING OF JUDGE|RULING \(NO", "Ruling"),
    (r"MINUTE OF JUDGE", "Minute"),
    (r"COSTS JUDGMENT|JUDGMENT AS TO COSTS", "Costs judgment"),
]


def find_citation(text):
    # The neutral citation of the document itself sits alone on a line in the header.
    # Search there first, so a case cited later in the text is not picked.
    head = text[:4000]
    m = re.search(r"^\s*\[(\d{4})\]\s*(NZ[A-Za-z]{2,5})\s*(\d+)\s*$", head, re.M)
    if not m:
        m = CITATION_RE.search(head) or CITATION_RE.search(text)
    return f"[{m.group(1)}] {m.group(2)} {m.group(3)}" if m else None


def find_court(text):
    m = COURT_RE.search(text[:2000])
    return m.group(1).title().replace(" Of ", " of ") if m else None


def find_registry(text):
    m = REGISTRY_RE.search(text[:3000])
    if m:
        return m.group(2).strip().title()
    return None


def find_file_number(text):
    m = FILE_NO_RE.search(text[:4000])
    return m.group(0) if m else None


def find_judgment_date(text):
    head = text[:5000]
    for m in DATE_LABEL_RE.finditer(head):
        d = DATE_RE.search(m.group(1))
        if d:
            return to_iso(*d.groups())
    # Running header: "X v Y [2021] NZDC 1851 [4 February 2021]"
    m = re.search(r"NZ(?:DC|YC)\s*\d+\s*\[(\d{1,2}\s+\w+\s+\d{4})\]", text)
    if m:
        d = DATE_RE.search(m.group(1))
        if d:
            return to_iso(*d.groups())
    m = re.search(r"Date of authentication\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})", text, re.I)
    if m:
        dd, mm, yy = m.groups()
        return f"{yy}-{int(mm):02d}-{int(dd):02d}"
    return None


def find_doc_type(text):
    head = flat(text[:4000])
    label = None
    for pat, name in DOC_TYPES:
        if re.search(pat, head, re.I):
            label = name
            break
    sub = re.search(r"\[\s*(On [^\]]{3,80})\]", head)
    if label and sub:
        return f"{label} ({sub.group(1).strip()})"
    if label:
        return label
    return sub.group(1).strip() if sub else None



# Sentencing fields



# Most specific first.
SENTENCE_TYPES = [
    ("discharge without conviction", r"discharge(?:d)? without conviction|s ?106 discharge"),
    ("conviction and discharge", r"convicted and discharged|conviction and discharge|s ?108"),
    ("home detention", r"home detention"),
    ("community detention", r"community detention"),
    ("intensive supervision", r"intensive supervision"),
    ("imprisonment", r"imprisonment|prison"),
    ("supervision", r"(?<!intensive )supervision"),
    ("community work", r"community work|hours'? of community"),
    ("fine", r"\bfined?\b|\bfine of\b"),
    ("reparation", r"reparation"),
    ("deferment", r"come up for sentence if called upon|deferred sentence"),
]

IMPOSE_RE = re.compile(
    r"(?:I\s+)?(?:now\s+)?(?:therefore\s+)?(?:sentence(?:d)?\s+(?:you|him|her|the defendant|(?:Mr|Ms|Mrs|Miss|Dr)\.?\s+[A-Z][\w'-]+|[A-Z][a-z]+)\s+to"
    r"|(?:am|are|is|be) imposing (?:a |an )?(?:sentence of )?"
    r"|(?:I|we) (?:will |now |therefore )?impose (?:a |an )?sentence of "
    r"|you are (?:now )?sentenced to|(?:is|are) sentenced to|\bimposes? (?:a|an)?"
    r"|I convert (?:that|the|this) (?:sentence|term|end sentence) (?:of imprisonment )?(?:in)?to"
    r"|(?:the )?(?:final|end) sentence (?:is|will be) (?:therefore )?"
    r"|(?:is|are) (?:also )?(?:fined|ordered to pay|convicted and discharged|discharged without conviction)"
    r"|(?:you|he|she|it) (?:is|are|will be) (?:also )?(?:fined|ordered to pay)"
    r"|fine of \$[\d,.]+ (?:is|was) imposed)",
    re.I)

END_SENTENCE_RE = re.compile(
    r"\b(?:end|final|resulting|total|effective) sentence\b|\bI arrive at\b|\bleaves? (?:an? )?(?:end )?sentence\b|\bresults? in (?:an? )?(?:end )?sentence\b",
    re.I)

PLEA_WORDS_RE = re.compile(r"guilty pleas?|\bplea\b|pleading guilty|pleaded guilty", re.I)
PCT_RE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:%|per\s?cent|percent)", re.I)
PCT_WORDS = {
    "a full quarter": 25, "one quarter": 25, "a quarter": 25, "one-quarter": 25,
    "one-third": 33, "one third": 33, "a third": 33,
    "one-fifth": 20, "one fifth": 20, "a fifth": 20,
    "one-tenth": 10, "one tenth": 10, "a tenth": 10,
    "half": 50,
}


def is_sentencing(text: str, doc_type: str | None) -> bool:
    if doc_type and "Sentencing" in doc_type:
        return True
    head = flat(text[:4000]).lower()
    return "on sentencing" in head or "sentencing notes" in head


def find_sentence_type(ft: str):
    """ft = flattened full text. Look at imposition phrases, last ones first."""
    hits = []
    for m in IMPOSE_RE.finditer(ft):
        window = ft[m.start(): m.end() + 160]
        for name, pat in SENTENCE_TYPES:
            tm = re.search(pat, window, re.I)
            if tm:
                hits.append((m.start(), name, snippet(ft, m.start(), m.start() + tm.end(), 60)))
                break
    if hits:
        main_pos, main, ev = hits[-1]
        # Prefer a custodial / community sentence over ancillary orders.
        ancillary = {"reparation", "fine"}
        core = [h for h in hits if h[1] not in ancillary]
        if core and main in ancillary:
            main_pos, main, ev = core[-1]
        # Earlier custodial mentions are usually steps in the reasoning
        # (e.g. imprisonment later converted to home detention), not extra orders.
        custodial = {"imprisonment", "home detention", "community detention"}
        others = sorted({h[1] for h in hits if h[1] != main
                         and not (main in custodial and h[1] in custodial)})
        return main, others, ev
    # Fallback: count mentions in the last 25 % of the document.
    tail = ft[int(len(ft) * 0.75):].lower()
    for name, pat in SENTENCE_TYPES:
        if re.search(pat, tail, re.I):
            m = re.search(pat, ft[int(len(ft) * 0.75):], re.I)
            s = int(len(ft) * 0.75) + m.start()
            return name, [], snippet(ft, s, s + len(m.group(0)), 80) + " [low confidence]"
    return None, [], None


def find_end_sentence(ft: str, sentence_type: str | None):
    """Return (months, home_or_community_detention_months, evidence)."""
    cands = []
    for m in END_SENTENCE_RE.finditer(ft):
        window = ft[m.end(): m.end() + 140]
        months, s, e = parse_duration(window)
        if months:
            cands.append((m.start(), months, snippet(ft, m.start(), m.end() + e, 50)))
    end_months, ev = (cands[-1][1], cands[-1][2]) if cands else (None, None)

    # Duration directly after an imposition phrase ("I sentence you to 2 years 3 months' imprisonment").
    imposed = []
    for m in IMPOSE_RE.finditer(ft):
        window = ft[m.end(): m.end() + 120]
        months, s, e = parse_duration(window)
        if months and s < 25:
            after = window[e: e + 40].lower()
            imposed.append((m.start(), months, after, snippet(ft, m.start(), m.end() + e, 50)))

    hd_months = None
    for pos, months, after, snip in imposed:
        if "home detention" in after or "community detention" in after:
            hd_months = months
    if end_months is None:
        custodial = [x for x in imposed if "imprisonment" in x[2] or "prison" in x[2]]
        pick = custodial[-1] if custodial else (imposed[-1] if imposed else None)
        if pick:
            end_months, ev = pick[1], pick[3]
    # Home detention without a stated imprisonment end sentence
    if end_months is None and hd_months is not None:
        end_months = hd_months
    return end_months, hd_months, ev


PLEA_STRONG_RE = re.compile(
    r"(\d{1,2}(?:\.\d+)?)\s*(?:%|per\s?cent|percent)\s+(?:discount\s+|reduction\s+|credit\s+)?"
    r"(?:is\s+(?:appropriate|available)\s+)?for\s+(?:the\s+|your\s+|his\s+|her\s+|its\s+|their\s+|an?\s+)?"
    r"(?:early\s+|prompt\s+|timely\s+|late\s+|later\s+)?(?:entry\s+of\s+(?:a|the|its|his|her)\s+)?"
    r"(?:guilty\s+)?pleas?\b"
    r"|(?:guilty\s+)?plea\s+(?:discount|reduction|credit)\s+(?:of\s+)?(\d{1,2}(?:\.\d+)?)\s*(?:%|per\s?cent|percent)"
    r"|(?:discount|reduction|deduction|credit)[^.\[]{0,80}?for\s+(?:the\s+|your\s+|his\s+|her\s+|its\s+|their\s+)?(?:early\s+)?guilty\s+pleas?"
    r",?\s+(?:which\s+is\s+|of\s+|at\s+|is\s+|was\s+)(\d{1,2}(?:\.\d+)?)\s*(?:%|per\s?cent|percent)",
    re.I)
TRIAL_RE = re.compile(
    r"following (?:a |the |your )?(?:defended hearing|trial|judge-alone trial|jury trial)"
    r"|after (?:a |the )?(?:defended hearing|trial)|found (?:you |him |her |it |the defendant )?guilty"
    r"|found the charges? proved|charges? (?:is|are|was|were) (?:found )?proved"
    r"|right to test the charge|convicted after (?:a )?(?:trial|defended hearing)"
    r"|(?:jury|court) (?:returned|found) (?:a )?(?:verdicts? of )?guilty",
    re.I)
TOTAL_DISCOUNT_RE = re.compile(
    r"(?:reduction|discount|deduction)s?\s+(?:of|totalling|totaling)\s+(\d{1,2})\s*(?:%|per\s?cent|percent)",
    re.I)


def find_guilty_plea_pct(ft: str):
    """Return (pct, evidence, note)."""
    strong = list(PLEA_STRONG_RE.finditer(ft))
    if strong:
        m = strong[-1]  # the court's final statement usually comes after submissions
        v = float(next(g for g in m.groups() if g))
        return (int(v) if v.is_integer() else v), snippet(ft, m.start(), m.end(), 60), None

    trial = TRIAL_RE.search(ft)
    own_plea = re.search(r"(?:you|has|have|it|she|he) (?:has |have )?(?:pleaded|pled|entered (?:a|your|its) )guilty"
                         r"|(?:your|its|his|her) guilty pleas?", ft, re.I)
    if trial and not own_plea:
        return 0, snippet(ft, trial.start(), trial.end(), 60), "No guilty plea: convicted after trial or defended hearing"

    best = None  # (distance, pct, evidence)
    for pm in PLEA_WORDS_RE.finditer(ft):
        ctx_start = max(0, pm.start() - 220)
        ctx = ft[ctx_start: pm.end() + 220]
        # Skip "not guilty" pleas
        if re.search(r"not guilty", ft[max(0, pm.start() - 12): pm.end()], re.I):
            continue
        for m in PCT_RE.finditer(ctx):
            val = float(m.group(1))
            if val > 40:  # NZ plea discounts are capped at 25 %; allow slack.
                continue
            abs_pos = ctx_start + m.start()
            between = ft[min(abs_pos, pm.start()): max(abs_pos, pm.end())]
            if re.search(r"\[\d+\]", between):  # crosses a paragraph
                continue
            dist = abs(abs_pos - pm.start())
            if best is None or dist < best[0]:
                best = (dist, val, snippet(ft, min(abs_pos, pm.start()), max(abs_pos + len(m.group(0)), pm.end()), 40))
        for w, val in PCT_WORDS.items():
            for m in re.finditer(r"\b" + re.escape(w) + r"\b", ctx, re.I):
                abs_pos = ctx_start + m.start()
                dist = abs(abs_pos - pm.start()) + 5  # slight preference for digits
                if best is None or dist < best[0]:
                    best = (dist, float(val), snippet(ft, min(abs_pos, pm.start()), max(abs_pos, pm.end()), 40))
    if best:
        v = best[1]
        return (int(v) if v.is_integer() else v), best[2], "Low confidence: percentage found near the word 'plea'"
    # Explicit "no discount for the plea"
    m = re.search(r"no (?:discount|credit|reduction) for (?:the|your|his|her|its) (?:guilty )?plea", ft, re.I)
    if m:
        return 0, snippet(ft, m.start(), m.end(), 40), None
    # Plea discount folded into one total discount
    totals = list(TOTAL_DISCOUNT_RE.finditer(ft))
    if totals and own_plea:
        m = totals[-1]
        return None, snippet(ft, m.start(), m.end(), 80), (
            f"Plea discount not stated on its own; total discount of {m.group(1)}% "
            "includes the plea and other factors")
    return None, None, None


FINE_RE = re.compile(
    r"(?:is|are|be) fined \$([\d,]+(?:\.\d{2})?)|impose (?:a|the) fine of \$([\d,]+(?:\.\d{2})?)"
    r"|fine of \$([\d,]+(?:\.\d{2})?) (?:is|was) imposed|(?:I|we) fine (?:you|it|him|her|the \w+) \$([\d,]+(?:\.\d{2})?)",
    re.I)


def find_fine(ft: str):
    hits = list(FINE_RE.finditer(ft))
    if not hits:
        return None
    m = hits[-1]
    amt = next(g for g in m.groups() if g)
    return float(amt.replace(",", ""))



# Main entry point



@dataclass
class Result:
    file_name: str
    citation: str | None = None
    court: str | None = None
    registry: str | None = None
    file_number: str | None = None
    judgment_date: str | None = None
    document_type: str | None = None
    is_sentencing: bool = False
    sentence_type: str | None = None
    other_orders: str | None = None
    end_sentence_months: float | None = None
    detention_months: float | None = None
    guilty_plea_pct: float | None = None
    fine_amount: float | None = None
    sentence_type_evidence: str | None = None
    end_sentence_evidence: str | None = None
    guilty_plea_evidence: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_row(self) -> dict:
        d = asdict(self)
        d["warnings"] = "; ".join(self.warnings)
        return d


def pdf_to_text(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def extract_from_text(text: str, file_name: str = "") -> Result:
    text = clean(text)
    r = Result(file_name=file_name)
    if len(text.strip()) < 200:
        r.warnings.append("No text layer found. The PDF may be a scan and needs OCR.")
        return r

    r.citation = find_citation(text)
    r.court = find_court(text)
    r.registry = find_registry(text)
    r.file_number = find_file_number(text)
    r.judgment_date = find_judgment_date(text)
    r.document_type = find_doc_type(text)
    r.is_sentencing = is_sentencing(text, r.document_type)

    if r.court and r.court != "District Court":
        r.warnings.append(f"Not a District Court document ({r.court})")
    for f in ("citation", "registry", "judgment_date", "document_type"):
        if getattr(r, f) is None and not (f == "registry" and r.court and r.court != "District Court"):
            r.warnings.append(f"{f} not found")

    if r.is_sentencing:
        ft = flat(text)
        r.sentence_type, others, r.sentence_type_evidence = find_sentence_type(ft)
        r.other_orders = ", ".join(others) or None
        r.end_sentence_months, r.detention_months, r.end_sentence_evidence = \
            find_end_sentence(ft, r.sentence_type)
        r.guilty_plea_pct, r.guilty_plea_evidence, note = find_guilty_plea_pct(ft)
        if note:
            r.warnings.append(note)
        if r.sentence_type == "fine" or "fine" in (r.other_orders or ""):
            r.fine_amount = find_fine(ft)
        if r.sentence_type in ("fine", "reparation", "discharge without conviction",
                               "conviction and discharge", "deferment"):
            # A non-custodial outcome has no end sentence in months.
            if r.end_sentence_months is None:
                r.warnings.append("No custodial end sentence (non-custodial outcome)")
        if r.sentence_type is None:
            r.warnings.append("sentence_type not found")
        if r.end_sentence_months is None and r.sentence_type not in (
                "fine", "reparation", "discharge without conviction", "conviction and discharge", "deferment"):
            r.warnings.append("end_sentence_months not found")
        if r.guilty_plea_pct is None and not note:
            r.warnings.append("guilty_plea_pct not found")
    return r


def extract_from_pdf(data: bytes, file_name: str) -> Result:
    try:
        text = pdf_to_text(data)
    except Exception as e:  # noqa: BLE001
        r = Result(file_name=file_name)
        r.warnings.append(f"Could not read PDF: {e}")
        return r
    return extract_from_text(text, file_name)
