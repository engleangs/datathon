"""Check that every PDF gives the same CSV structure and the right values.

Run: python -m pytest -q
"""
import csv
import io
import os

import pytest

from schema import COLUMNS, pdf_to_row, rows_to_csv

SAMPLES = os.path.join(os.path.dirname(__file__), "samples")

EXPECTED = {
    "1851.pdf": ["[2021] NZDC 1851", "Greymouth", "2021-02-04",
                 "Reserved judgment (On Pre-Trial Application)", "", "", ""],
    "587.pdf":  ["[2018] NZCA 587", "", "2018-12-14", "Judgment", "", "", ""],
    "785.pdf":  ["[2022] NZDC 785", "Auckland", "2022-01-20", "Sentencing notes",
                 "imprisonment", "36", "0"],
    "2078.pdf": ["[2023] NZDC 2078", "Tauranga", "2024-02-02", "Sentencing decision",
                 "fine", "", "25"],
    "5627.pdf": ["[2022] NZDC 5627", "Auckland", "2022-03-31", "Sentencing notes",
                 "fine", "", ""],
    "7870.pdf": ["[2022] NZDC 7870", "Kaikoura", "2022-04-28", "Sentencing notes",
                 "fine", "", "0"],
    "8837.pdf": ["[2025] NZDC 8837", "Auckland", "2025-02-17", "Sentencing notes",
                 "home detention", "24", "25"],
}


def _row(name):
    path = os.path.join(SAMPLES, name)
    if not os.path.exists(path):
        pytest.skip(f"{name} not in samples/")
    with open(path, "rb") as f:
        return pdf_to_row(f.read(), name)


@pytest.mark.parametrize("name", EXPECTED)
def test_values(name):
    row = _row(name)
    assert list(row) == COLUMNS
    assert [row[c] for c in COLUMNS[1:]] == EXPECTED[name]


def test_same_structure_for_every_pdf():
    rows = [_row(n) for n in EXPECTED]
    # One CSV for all PDFs
    all_csv = list(csv.reader(io.StringIO(rows_to_csv(rows))))
    assert all_csv[0] == COLUMNS
    assert all(len(r) == len(COLUMNS) for r in all_csv)
    # One CSV per PDF: every file has the same header and one data row
    for row in rows:
        single = list(csv.reader(io.StringIO(rows_to_csv([row]))))
        assert single[0] == COLUMNS and len(single) == 2


def test_unreadable_pdf_still_gives_full_row():
    row = pdf_to_row(b"not a pdf", "broken.pdf")
    assert list(row) == COLUMNS
    assert row["file_name"] == "broken.pdf"
