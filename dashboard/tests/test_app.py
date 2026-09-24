"""Headless tests for streamlit_app.py. Run from this folder:  pytest -q tests"""
from pathlib import Path

import fake_snowflake  # noqa: F401  (installs the fake Snowflake session)
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "streamlit_app.py")

# Test data (tests/fake_snowflake.py): 10 judgments; j10 is unverified,
# j9 has a publication-restriction marker: listed with a warning badge, details locked.


def run(at):
    at.run(timeout=30)
    assert not at.exception, [e.message for e in at.exception]
    return at


def results_label(at):
    return next(m.value for m in at.markdown if "results" in m.value)


def kpi_values(at):
    return [m.value for m in at.markdown if 'class="kpi"' in m.value]


def app_functions():
    """Load the pure helper functions without running the Streamlit page."""
    src = open(APP, encoding="utf-8").read()
    ns = {"alt": __import__("altair"), "pd": __import__("pandas"), "re": __import__("re")}
    exec(src[src.index("KEEP_UPPER"):src.index("def fmt_date")], ns)
    exec(src[src.index("def count_axis"):src.index("def horizontal_bars")], ns)
    return ns


def test_overview_shows_all_judgments_by_default():
    at = run(AppTest.from_file(APP))
    assert at.title[0].value == "From judgments to insights"
    assert '<div class="num">10</div><div class="lbl">Judgments</div>' in kpi_values(at)[1]
    assert any(m.value.startswith("- ") for m in at.markdown)


def test_verified_only_checkbox_narrows():
    at = run(AppTest.from_file(APP))
    assert at.sidebar.checkbox(key="verified_only").value is False
    at.sidebar.checkbox(key="verified_only").check()
    run(at)
    assert '<div class="num">9</div>' in kpi_values(at)[1]      # j10 unverified


def test_search_filter_select_paginate_reset():
    at = run(AppTest.from_file(APP))
    at.text_input(key="overview_search").set_value("alpha")
    run(at)
    assert at.session_state["nav"] == "Case Explorer"
    assert results_label(at) == "**Cases** (3 results)"      # alpha 3, 6, 9
    [b for b in at.button if b.label == "Reset filters"][0].click()
    run(at)
    assert results_label(at) == "**Cases** (10 results)"
    [b for b in at.button if b.label == "Next"][0].click()
    run(at)
    assert at.session_state["page_no"] == 2
    at.selectbox(key="f_location").set_value("Auckland")
    run(at)
    assert results_label(at) == "**Cases** (5 results)" and at.session_state["page_no"] == 1
    [b for b in at.button if b.key and b.key.startswith("case_")][0].click()
    run(at)
    assert at.header[0].value


def test_case_details_citations_dollars_and_judges():
    at = run(AppTest.from_file(APP))
    [b for b in at.button if b.key == "recent_j1"][0].click()
    run(at)
    text = " ".join(m.value for m in at.markdown)
    assert "Henderson v R [2017] NZCA 605" in text
    assert "Customs and Excise Act 2018 s 371" in text
    assert "OLD" not in at.header[0].value                   # latest extraction used
    assert "\\$33,500" in text                               # $ escaped, not rendered as maths
    assert "D A Kirkpatrick" in text


def test_restricted_judgment_listed_but_details_locked():
    at = run(AppTest.from_file(APP))
    at.sidebar.radio[0].set_value("Case Explorer")
    at.session_state["selected_key"] = "j9"
    run(at)
    assert any(b.key == "case_j9" for b in at.button)              # still in the list
    text = " ".join(m.value for m in at.markdown)
    assert "Check publication restriction" in text                 # badge shown
    assert any("details are withheld" in w.value for w in at.warning)
    assert len(at.tabs) == 0                                       # no details tabs
    assert "Supporting evidence" not in text and "Outcome" not in text


def test_unrestricted_judgment_still_opens():
    at = run(AppTest.from_file(APP))
    at.sidebar.radio[0].set_value("Case Explorer")
    at.session_state["selected_key"] = "j1"
    run(at)
    assert len(at.tabs) == 3


def test_pages_and_no_about():
    at = run(AppTest.from_file(APP))
    assert at.sidebar.radio[0].options == ["Overview", "Case Explorer", "Insights"]
    at.sidebar.radio[0].set_value("Insights")
    run(at)


def test_judge_names_merge_to_one_spelling():
    f = app_functions()["judge_display"]
    assert f("E M THOMAS") == f("EM Thomas") == f("Judge E M Thomas") == "E M Thomas"
    assert f("DA KIRKPATRICK") == "D A Kirkpatrick"
    assert f("J J M HASSAN") == f("JJM Hassan") == "J J M Hassan"
    assert f("GLAZEBROOK J") == "Glazebrook J"
    assert f("Ellen France J") == "Ellen France J"


def test_count_axis_whole_numbers():
    ns = app_functions()
    axis = ns["count_axis"](ns["pd"].Series([1, 2, 5]))
    assert axis.values == [0, 1, 2, 3, 4, 5]
