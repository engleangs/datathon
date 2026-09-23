"""One fixed CSV structure for every PDF.

Every PDF gives exactly one row with these columns, in this order,
whatever the type of document. A field that does not apply is empty.
"""
import csv
import io

from extractor import extract_from_pdf

COLUMNS = [
    "file_name",
    "citation",
    "registry",
    "judgment_date",
    "document_type",
    "sentence_type",        # sentencing notes only
    "end_sentence_months",  # sentencing notes only
    "guilty_plea_pct",      # sentencing notes only
]
SENTENCING_ONLY = ["sentence_type", "end_sentence_months", "guilty_plea_pct"]


def _fmt(v):
    """Numbers without a trailing .0, None as an empty cell."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def pdf_to_row(data: bytes, file_name: str) -> dict:
    r = extract_from_pdf(data, file_name)
    row = {c: getattr(r, c, None) for c in COLUMNS}
    row["file_name"] = file_name
    if not r.is_sentencing:
        for c in SENTENCING_ONLY:
            row[c] = None
    return {c: _fmt(row[c]) for c in COLUMNS}


def rows_to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="raise")
    w.writeheader()
    for row in rows:
        w.writerow({c: row.get(c, "") for c in COLUMNS})
    return buf.getvalue()
