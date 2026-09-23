"""Run: python -m pytest app/tests -q   (from the project root)"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pdf_extract import duration_to_months, read_pdf  # noqa: E402

SAMPLES = Path(__file__).resolve().parents[1] / "sample_pdfs"


def load(name):
    return read_pdf((SAMPLES / name).read_bytes(), name)


def test_sentencing_note_fields():
    r = load("SYNTHETIC_dc_sentencing.pdf")
    assert r.neutral_citation == "[2025] NZDC 18765"
    assert r.registry == "Manukau"
    assert r.case_type == "criminal"
    assert r.document_type == "sentencing"
    assert r.judge == "Judge A B Example"
    assert r.starting_point_months == 36
    assert r.end_sentence_months == 20
    assert r.home_detention_months == 10
    assert r.sentence_type == "home detention"
    assert r.guilty_plea_pct == 25
    assert r.personal_mitigation_pct == 25
    assert r.reparation_nzd == 1500
    assert r.reform_period == "after reform"
    assert r.publication_note and "S 203" in r.publication_note.upper()


def test_civil_fields():
    r = load("SYNTHETIC_dc_civil.pdf")
    assert r.case_type == "civil"
    assert r.document_type == "reserved judgment"
    assert r.amount_claimed_nzd == 48000
    assert r.amount_awarded_nzd == 32500
    assert r.reform_period == "before reform"


def test_youth_court_is_excluded_and_text_dropped():
    r = load("SYNTHETIC_youth_court_should_be_excluded.pdf")
    assert r.excluded_reason == "youth_court"
    assert r.pages == []
    assert not r.is_usable


def test_not_a_pdf():
    r = read_pdf(b"<html>error page</html>", "x.pdf")
    assert r.error and not r.is_usable


def test_durations():
    assert duration_to_months("2 years and 6 months") == 30
    assert duration_to_months("eighteen months") == 18
    assert duration_to_months("three years") == 36
    assert duration_to_months("6 weeks") == 1.5
    assert duration_to_months("no number here") is None
