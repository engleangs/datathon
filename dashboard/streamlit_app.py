# CourtLens dashboard
#
# This app shows New Zealand court judgments that our pipeline has already
# extracted and stored in Snowflake. It has three pages:
#   Overview       - headline numbers and charts
#   Case Explorer  - search and open a single judgment with its evidence
#   Insights       - patterns across judgments and how reliable the AI output is
#
# All data comes from the dbt models in DATATHON_TEST.ANALYTICS_ANALYTICS.
# The app only reads data. It never writes anything back to Snowflake.
# Judgments flagged for a possible publication restriction (for example a
# suppression order) appear in the list with a warning badge, but their
# details are locked: clicking one shows only a notice, not the contents.

import json
import re

import altair as alt
import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

# Where our tables live, and which warehouse runs the queries.
# If a query runs without a warehouse, Snowflake refuses it.
DB_SCHEMA = "DATATHON_TEST.ANALYTICS_ANALYTICS"
WAREHOUSE = "DTH_WH"

# How many cases to list per page in the Case Explorer.
PAGE_SIZE = 8

# Colours used across the app, matched to the design mockup.
NAVY = "#2B2A6B"
BLUE = "#3B6FE0"
PINK = "#F2557A"
GREEN = "#4CB782"
AMBER = "#F5C542"
PURPLE = "#4B3FC8"
PALETTE = [BLUE, PINK, GREEN, AMBER, "#8E7CE0", "#2BB3C0", "#9AA0B8"]

st.set_page_config(page_title="CourtLens", page_icon="⚖️", layout="wide")

# Custom styling: the dark blue sidebar, the white KPI cards, and the small
# coloured "pill" badges (Verified, Needs review and so on).
st.markdown(f"""
<style>
[data-testid="stSidebar"] {{ background: {NAVY}; }}
[data-testid="stSidebar"] * {{ color: #FFFFFF; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding: 6px 4px; }}
.block-container {{ padding-top: 2rem; }}
.eyebrow {{ color: #5A5F7A; font-weight: 600; letter-spacing: .06em; margin-bottom: 0; }}
.kpi {{ background: #FFFFFF; border: 1px solid #E4E7F2; border-radius: 12px; padding: 14px 18px; }}
.kpi .num {{ font-size: 1.9rem; font-weight: 700; color: #1C1D3A; line-height: 1.1; }}
.kpi .lbl {{ color: #5A5F7A; }}
.pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .8rem;
         background: #E8EEFD; color: {BLUE}; }}
.pill.warn {{ background: #FDE8EE; color: {PINK}; }}
.pill.ok {{ background: #E6F6EE; color: #2E8B5E; }}
.muted {{ color: #6B7090; font-size: .85rem; }}
.note {{ background: #EEF2FD; border-radius: 10px; padding: 10px 14px; color: #2B2F55; }}
</style>
""", unsafe_allow_html=True)


# ============================================================================
# Cleaning up text for display
# ============================================================================

# Words that must stay in capitals (like "NZ" or the "J" after a judge's name)
# and small words that should stay lower case in the middle of a title.
KEEP_UPPER = {"NZ", "R", "QC", "KC", "CJ", "J", "JJ", "P", "SC", "CA", "HC", "DC", "ACC", "IRD"}
LOWER_WORDS = {"v", "and", "of", "the", "for", "as", "in", "on", "to", "a", "an", "by", "at"}


def title_case(text):
    # Turns shouty text like "DISTRICT COURT" into "District Court".
    # First we tidy up any double spaces.
    text = re.sub(r"\s+", " ", str(text or "")).strip()

    # If the text is already mostly lower case, someone typed it properly,
    # so we leave it exactly as it is.
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) / len(letters) < 0.7:
        return text

    # Otherwise go word by word: keep abbreviations in capitals, keep small
    # joining words lower case, and capitalise everything else.
    out = []
    for i, word in enumerate(text.split(" ")):
        core = word.strip("(),.;:")
        if core.upper() in KEEP_UPPER:
            out.append(word.lower() if core.upper() == "V" else word.upper())
        elif i > 0 and core.lower() in LOWER_WORDS:
            out.append(word.lower())
        else:
            # Capitalise each part separately, so O'REGAN becomes O'Regan.
            out.append(re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize(), word))
    return " ".join(out)


def split_court(name):
    # Our data has no separate location column. The court name holds it,
    # e.g. "DISTRICT COURT AT AUCKLAND", so we split it into
    # ("District Court", "Auckland").
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name:
        return "Unknown", "Unknown"
    m = re.match(r"^(.*?COURT)(?: OF NEW ZEALAND)?(?: AT (.+))?$", name, re.I)
    court = title_case(m.group(1)) if m else title_case(name)
    if m and m.group(2):
        return court, title_case(m.group(2))
    # The Supreme Court always sits in Wellington. For anything else without
    # "AT ..." in the name, we honestly don't know the location.
    return court, "Wellington" if "SUPREME" in name.upper() else "Unknown"


def md_safe(text):
    # Streamlit treats text between two "$" signs as a maths formula, which
    # turned "fine of $17,000 ... $152" into strange code-style text.
    # Putting a backslash before each "$" makes it show as a normal dollar sign.
    return str(text).replace("$", "\\$")


def judge_display(name):
    # The same judge can be written several ways in the data:
    # "E M THOMAS", "EM Thomas", "Judge E M Thomas". If we don't merge them,
    # one judge appears twice in the charts. This gives every judge a single
    # spelling, e.g. "E M Thomas", "D A Kirkpatrick", "Glazebrook J".
    raw = re.sub(r"\s+", " ", str(name or "")).strip()

    # Drop a leading "Judge" or "Justice", since it's not part of the name.
    raw = re.sub(r"^(Judge|Justice)\s+", "", raw, flags=re.I)
    if not raw:
        return raw

    # Set aside a title at the end, like the "J" in "Glazebrook J".
    tokens = raw.split(" ")
    suffix = [tokens.pop()] if len(tokens) > 1 and tokens[-1] in ("J", "CJ", "P", "JJ") else []
    if not tokens:
        return raw

    # Only change capitalisation for words written in all capitals.
    def word(t):
        return title_case(t) if t.isupper() else t

    # Short capital words before the surname are initials run together,
    # so "EM" becomes "E M". Longer ones like "ELLEN" are first names.
    initials = []
    for t in tokens[:-1]:
        initials += list(t) if t.isalpha() and t.isupper() and len(t) <= 3 else [word(t)]
    return " ".join(initials + [word(tokens[-1])] + suffix)


def citation_year(citation):
    # Pulls the year out of a citation, e.g. "[2023] NZDC 2078" gives 2023.
    # We use it to spot judgments whose extracted date doesn't match.
    m = re.search(r"\[(\d{4})\]", str(citation or ""))
    return int(m.group(1)) if m else None


def fmt_date(value, pattern="%d %b %Y"):
    # Shows a date like "20 Jan 2022", or says so plainly if it's missing.
    return value.strftime(pattern) if pd.notna(value) else "Date unknown"


# ============================================================================
# Getting data from Snowflake
#
# Our dataset is small, so we run each query once, keep the result in memory
# for 10 minutes, and do all the filtering in pandas. Nothing the user types
# ever goes into a SQL query, so the app can't be used to run unwanted SQL.
# ============================================================================

def get_session():
    # Connects to Snowflake. Older Streamlit apps connect one way and newer
    # container-based apps (like ours, which has a pyproject.toml) connect
    # another way, so we try the first and fall back to the second.
    try:
        session = get_active_session()
    except Exception:
        session = st.connection("snowflake").session()

    # Make sure queries run on our team's warehouse. If that fails we show a
    # warning rather than crashing, because the queries might still work.
    try:
        session.use_warehouse(WAREHOUSE)
    except Exception as exc:
        st.warning(f"Could not switch to warehouse {WAREHOUSE}: {exc}")
    return session


def run_query(sql):
    # Runs a query and returns the result as a pandas table.
    # Column names are made upper case so the rest of the code can rely on it.
    df = get_session().sql(sql).to_pandas()
    df.columns = [c.upper() for c in df.columns]
    return df


S = DB_SCHEMA

# Every query the app needs, in one place, so they're easy to review.
SQL = {
    # One row per judgment. If a PDF was extracted more than once, we keep
    # only the newest extraction (the QUALIFY line does that). We also join
    # in the court name, case category and source file details.
    "judgments": f"""
        WITH j AS (
            SELECT * FROM {S}.FCT_JUDGMENT
            QUALIFY ROW_NUMBER() OVER (PARTITION BY document_id
                                       ORDER BY extracted_at DESC NULLS LAST) = 1
        )
        SELECT j.judgment_key, j.document_id, j.case_name, j.neutral_citation,
               j.judgment_date, j.outcome, j.extraction_status,
               j.agent_needs_human_review, j.is_verified_for_default_analytics,
               j.evidence_verified, j.evidence_total, j.model_id, j.extracted_at,
               c.court_name, cc.case_category_name,
               d.filename, d.source_url, d.page_count
        FROM j
        LEFT JOIN {S}.DIM_COURT c            ON c.court_key = j.court_key
        LEFT JOIN {S}.DIM_CASE_CATEGORY cc   ON cc.case_category_key = j.case_category_key
        LEFT JOIN {S}.DIM_SOURCE_DOCUMENT d  ON d.document_id = j.document_id
    """,
    # Which judges sat on which judgment.
    "judges": f"""
        SELECT b.judgment_key, b.judge_position, dj.judge_name
        FROM {S}.BRIDGE_JUDGMENT_JUDGE b
        JOIN {S}.DIM_JUDGE dj ON dj.judge_key = b.judge_key
    """,
    # The legal topics tagged on each judgment.
    "topics": f"""
        SELECT b.judgment_key, b.topic_position, t.topic_name
        FROM {S}.BRIDGE_JUDGMENT_TOPIC b
        JOIN {S}.DIM_TOPIC t ON t.topic_key = b.topic_key
    """,
    # The legal questions each judgment deals with.
    "issues": f"""
        SELECT judgment_key, issue_position, issue_text
        FROM {S}.FCT_JUDGMENT_LEGAL_ISSUE
    """,
    # Earlier cases each judgment refers to, with the page and quote as proof.
    "case_citations": f"""
        SELECT f.judgment_key, dc.cited_case_name, dc.citation, dc.cited_judgment_key,
               f.reference_position, f.evidence_page, f.evidence_text
        FROM {S}.FCT_CASE_CITATION f
        LEFT JOIN {S}.DIM_CITED_CASE dc ON dc.cited_case_key = f.cited_case_key
    """,
    # Acts and sections each judgment refers to, again with the proof.
    "legislation": f"""
        SELECT f.judgment_key, dl.act_name, f.section,
               f.reference_position, f.evidence_page, f.evidence_text
        FROM {S}.FCT_LEGISLATION_CITATION f
        LEFT JOIN {S}.DIM_LEGISLATION dl ON dl.legislation_key = f.legislation_key
    """,
    # Quotes from the PDF that back up what the AI extracted.
    "evidence": f"""
        SELECT judgment_key, evidence_position, evidence_page, evidence_text
        FROM {S}.FCT_JUDGMENT_EVIDENCE
    """,
    # Problems the pipeline found, e.g. a quote it couldn't find in the PDF,
    # or a sign that the judgment has a publication restriction.
    "quality": f"""
        SELECT judgment_key, issue_type, issue_position, issue_text
        FROM {S}.FCT_JUDGMENT_QUALITY_ISSUE
    """,
}


# Runs one of the queries above by name. The result is remembered for
# 10 minutes (ttl=600 seconds) so we don't hit Snowflake on every click.
@st.cache_data(ttl=600)
def load(name):
    return run_query(SQL[name])


def safe_load(name):
    # Same as load(), but if something goes wrong (a table is missing, or we
    # don't have permission) it shows a clear message instead of a long error.
    try:
        return load(name)
    except Exception as exc:
        st.error(f"Could not load '{name}' from {DB_SCHEMA}. Check that the dbt models have run "
                 f"and the app's role can read them. Details: {exc}")
        st.stop()


# Builds the main table the whole app uses: one row per judgment, with
# everything already cleaned up and ready to display.
@st.cache_data(ttl=600)
def load_judgments_enriched():
    df = load("judgments").copy()

    # Turn the dates into real dates and pull out the year for the filters.
    df["JUDGMENT_DATE"] = pd.to_datetime(df["JUDGMENT_DATE"], errors="coerce")
    df["YEAR"] = df["JUDGMENT_DATE"].dt.year

    # Split "DISTRICT COURT AT AUCKLAND" into a court and a location.
    courts = df["COURT_NAME"].apply(split_court)
    df["COURT"] = [c for c, _ in courts]
    df["LOCATION"] = [l for _, l in courts]

    # Tidy the category and case name. A missing category is shown as
    # "Uncategorised" rather than a blank.
    df["CATEGORY"] = df["CASE_CATEGORY_NAME"].fillna("").map(title_case).replace("", "Uncategorised")
    df["CASE_NAME"] = df["CASE_NAME"].fillna("").map(title_case)

    # Replace empty text values with "" so searching and joining text is safe.
    for col in ("NEUTRAL_CITATION", "OUTCOME", "FILENAME", "SOURCE_URL", "EXTRACTION_STATUS", "MODEL_ID"):
        df[col] = df[col].fillna("")

    # Make sure the evidence counts are whole numbers (missing means 0).
    df["EVIDENCE_VERIFIED"] = pd.to_numeric(df["EVIDENCE_VERIFIED"], errors="coerce").fillna(0).astype(int)
    df["EVIDENCE_TOTAL"] = pd.to_numeric(df["EVIDENCE_TOTAL"], errors="coerce").fillna(0).astype(int)

    # Simple yes/no columns for the status badges.
    df["VERIFIED"] = df["IS_VERIFIED_FOR_DEFAULT_ANALYTICS"].fillna(False).astype(bool)
    df["NEEDS_REVIEW"] = df["AGENT_NEEDS_HUMAN_REVIEW"].fillna(False).astype(bool)

    # Build a readable list of judges for each judgment, e.g. "D A Kirkpatrick, S M Tepania",
    # keeping the order they appear in and skipping duplicates.
    judges = load("judges").copy()
    judges["JUDGE_NAME"] = judges["JUDGE_NAME"].map(judge_display)
    judge_lists = (judges.sort_values(["JUDGMENT_KEY", "JUDGE_POSITION"])
                   .groupby("JUDGMENT_KEY")["JUDGE_NAME"].apply(lambda s: ", ".join(dict.fromkeys(s))))

    # Same idea for the legal topics.
    topics = load("topics")
    topic_lists = (topics.sort_values(["JUDGMENT_KEY", "TOPIC_POSITION"])
                   .groupby("JUDGMENT_KEY")["TOPIC_NAME"].apply(lambda s: ", ".join(dict.fromkeys(s))))

    # Mark any judgment where the pipeline found signs of a publication
    # restriction (for example a suppression order). These stay in the list
    # with a warning badge, but their details can't be opened.
    quality = load("quality")
    restricted = quality[quality["ISSUE_TYPE"].fillna("").str.upper().str.contains("PUBLICATION")]
    df["RESTRICTED"] = df["JUDGMENT_KEY"].isin(restricted["JUDGMENT_KEY"])

    df["JUDGES"] = df["JUDGMENT_KEY"].map(judge_lists).fillna("")
    df["TOPICS"] = df["JUDGMENT_KEY"].map(topic_lists).fillna("")

    # Newest judgments first.
    return df.sort_values("JUDGMENT_DATE", ascending=False).reset_index(drop=True)


def current_judgments():
    # The judgments the pages should actually show right now.
    try:
        df = load_judgments_enriched()
    except Exception as exc:
        st.error(f"Could not load judgments from {DB_SCHEMA}. Details: {exc}")
        st.stop()

    # If the "Verified judgments only" box is ticked, keep only verified ones.
    if st.session_state.get("verified_only", False):
        df = df[df["VERIFIED"]]
    return df


def for_judgments(name, keys):
    # Loads one of the detail tables (judges, topics, citations ...) and keeps
    # only the rows that belong to the judgments we're currently showing.
    df = safe_load(name)
    return df[df["JUDGMENT_KEY"].isin(keys)]


# ============================================================================
# Small building blocks for the screen
# ============================================================================

def kpi(col, number, label):
    # One white number card, like "13 Judgments". It's written on a single
    # line on purpose: if the HTML is indented, Streamlit shows it as code.
    col.markdown(f'<div class="kpi"><div class="num">{number:,}</div>'
                 f'<div class="lbl">{label}</div></div>', unsafe_allow_html=True)


def pill(text, kind=""):
    # A small rounded badge. "ok" makes it green, "warn" makes it pink.
    return f'<span class="pill {kind}">{text}</span>'


def status_pill(row):
    # Picks the right badge for a judgment. A possible publication restriction
    # comes first, then "Needs review", because those are the things a reader
    # most needs to know before using the case.
    if row["RESTRICTED"]:
        return pill("Check publication restriction", "warn")
    if row["NEEDS_REVIEW"]:
        return pill("Needs review", "warn")
    return pill("Verified", "ok") if row["VERIFIED"] else pill("Unverified")


def count_axis(values):
    # Chart axis for counting things. You can't have 0.5 of a judgment, so we
    # list the ticks ourselves: 0, 1, 2, 3 ... up to the biggest value.
    # For large numbers that would be too many ticks, so we just ask for whole numbers.
    top = int(pd.to_numeric(values, errors="coerce").fillna(0).max()) if len(values) else 0
    if top <= 20:
        return alt.Axis(format="d", values=list(range(0, top + 1)))
    return alt.Axis(format="d", tickMinStep=1)


def horizontal_bars(data, label_col, value_col, colour, height=240):
    # The sideways bar chart used for judges, locations, topics and so on.
    # Bars are sorted biggest first, and long names get enough room (labelLimit).
    chart = alt.Chart(data).mark_bar(color=colour, cornerRadiusEnd=3).encode(
        x=alt.X(f"{value_col}:Q", title=None, axis=count_axis(data[value_col])),
        y=alt.Y(f"{label_col}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
        tooltip=[label_col, value_col],
    )
    # Write the number at the end of each bar.
    text = chart.mark_text(align="left", dx=4, color="#1C1D3A").encode(text=f"{value_col}:Q")
    st.altair_chart((chart + text).properties(height=height), use_container_width=True)


def apply_search(df, term):
    # Keeps judgments whose name, citation, judges, topics, outcome, file name
    # or category contain the search words. Upper/lower case doesn't matter.
    if not term:
        return df
    term = term.strip().lower()
    haystack = (df["CASE_NAME"] + " " + df["NEUTRAL_CITATION"] + " " + df["JUDGES"] + " "
                + df["TOPICS"] + " " + df["OUTCOME"] + " " + df["FILENAME"] + " " + df["CATEGORY"]).str.lower()
    return df[haystack.str.contains(term, regex=False)]


# The next few functions run when someone clicks a button or changes a box.
# Streamlit runs them just before it redraws the page, which is the only safe
# moment to change what's selected, what page we're on, and so on.

def open_case(key):
    # Clicking a case under "Recent judgments" jumps to the Case Explorer
    # with that case already open.
    st.session_state["nav"] = "Case Explorer"
    st.session_state["selected_key"] = key


def search_from_overview():
    # Pressing Enter in the Overview search box takes you to the Case Explorer
    # with the same search already filled in, then clears the Overview box.
    term = st.session_state.get("overview_search", "").strip()
    if term:
        st.session_state["nav"] = "Case Explorer"
        st.session_state["search"] = term
        st.session_state["page_no"] = 1
        st.session_state["overview_search"] = ""


def select_case(key):
    # Remembers which case is open in the Case Explorer.
    st.session_state["selected_key"] = key


def set_page(n):
    # Moves the case list to page n (also used to go back to page 1
    # whenever a filter changes).
    st.session_state["page_no"] = n


def reset_filters():
    # Puts all the filters and the search box back to their starting values.
    for key in ("f_year", "f_judge", "f_category", "f_location", "search"):
        st.session_state.pop(key, None)
    st.session_state["page_no"] = 1


def empty_state():
    # What to show when there's nothing to display, with a hint on how to fix it.
    if st.session_state.get("verified_only", False):
        st.warning("No verified judgments yet. Turn off 'Verified judgments only' in the sidebar "
                   "to include judgments still awaiting verification.")
    else:
        st.warning(f"No judgments found in {DB_SCHEMA}. Run the dbt models, then refresh.")
    st.stop()


# ============================================================================
# Page 1: Overview
# ============================================================================

def judgments_over_time(df):
    # Line chart of how many judgments we have per year or month.
    dated = df.dropna(subset=["JUDGMENT_DATE"])
    if dated.empty:
        st.info("No judgment dates available.")
        return

    # If the data covers 3 or more years, count per year.
    # If it's shorter, count per month, otherwise the line would be a single dot.
    if dated["JUDGMENT_DATE"].dt.year.nunique() >= 3:
        dated = dated.assign(PERIOD=dated["JUDGMENT_DATE"].dt.year.astype(str))
        x_title = "Year"
    else:
        dated = dated.assign(PERIOD=dated["JUDGMENT_DATE"].dt.strftime("%Y-%m"))
        x_title = "Month"

    counts = dated.groupby("PERIOD").size().reset_index(name="Judgments")
    line = alt.Chart(counts).mark_line(point=True, color=BLUE).encode(
        x=alt.X("PERIOD:O", title=x_title), y=alt.Y("Judgments:Q", title="Number of judgments", axis=count_axis(counts["Judgments"])),
        tooltip=["PERIOD", "Judgments"])
    # A light shaded area under the line, to match the mockup.
    area = alt.Chart(counts).mark_area(color=BLUE, opacity=0.08).encode(x="PERIOD:O", y="Judgments:Q")
    st.altair_chart((area + line).properties(height=260), use_container_width=True)


def category_donut(df):
    # Donut chart showing what share of judgments falls in each case category.
    counts = df.groupby("CATEGORY").size().reset_index(name="Judgments")
    counts["Share"] = (counts["Judgments"] / counts["Judgments"].sum() * 100).round(0)
    base = alt.Chart(counts).encode(
        theta=alt.Theta("Judgments:Q", stack=True),
        color=alt.Color("CATEGORY:N", title=None, scale=alt.Scale(range=PALETTE)),
        tooltip=["CATEGORY", "Judgments", alt.Tooltip("Share:Q", format=".0f", title="Share %")],
    )
    donut = base.mark_arc(innerRadius=60, outerRadius=110)
    # The percentage printed just outside each slice.
    labels = base.mark_text(radius=135, size=12).encode(text=alt.Text("Share:Q", format=".0f"))
    st.altair_chart((donut + labels).properties(height=280), use_container_width=True)


def judge_counts(df):
    # How many of the shown judgments each judge sat on, most first.
    # Names are merged first, so "EM Thomas" and "E M Thomas" count as one person.
    judges = for_judgments("judges", df["JUDGMENT_KEY"]).copy()
    judges["JUDGE_NAME"] = judges["JUDGE_NAME"].map(judge_display)
    return (judges.groupby("JUDGE_NAME")["JUDGMENT_KEY"].nunique()
            .reset_index(name="Judgments").sort_values("Judgments", ascending=False))


def key_insights(df, judges):
    # The "Key insights" bullet points. Every sentence is worked out from the
    # data on screen. None of it is typed in by hand, so it's always true.
    notes = []

    cat = df["CATEGORY"].value_counts()
    notes.append(f"{cat.index[0]} is the largest category ({cat.iloc[0] / len(df):.0%} of judgments).")

    loc = df["LOCATION"].value_counts()
    notes.append(f"{loc.index[0]} accounts for {loc.iloc[0]} of {len(df)} judgments.")

    if not judges.empty:
        notes.append(f"{judges.iloc[0]['JUDGE_NAME']} appears on the most judgments ({int(judges.iloc[0]['Judgments'])}).")

    topics = for_judgments("topics", df["JUDGMENT_KEY"])
    if not topics.empty:
        t = topics["TOPIC_NAME"].value_counts()
        notes.append(f"Most common legal topic: {t.index[0]} ({t.iloc[0]} judgments).")

    # What share of the AI's supporting quotes were actually found in the PDFs.
    total = df["EVIDENCE_TOTAL"].sum()
    if total:
        notes.append(f"{df['EVIDENCE_VERIFIED'].sum() / total:.0%} of evidence quotes were verified "
                     f"against the source PDFs.")

    for n in notes:
        st.markdown(f"- {n}")


def page_overview():
    df = current_judgments()
    if df.empty:
        empty_state()

    # Top row: the search box, and when the data was last extracted.
    top_left, top_right = st.columns([4, 1])
    top_left.text_input("Search", placeholder="Search cases, judges, topics… (press Enter)",
                        label_visibility="collapsed", key="overview_search", on_change=search_from_overview)
    top_right.markdown(f'<div class="note">Last updated<br><b>{fmt_date(pd.to_datetime(df["EXTRACTED_AT"]).max())}</b></div>',
                       unsafe_allow_html=True)

    # Heading. The small line above the title lists the courts in the data.
    courts = sorted(c for c in df["COURT"].unique() if c and c != "Unknown")
    st.markdown(f'<p class="eyebrow">{" / ".join(courts) or "New Zealand courts"}</p>', unsafe_allow_html=True)
    st.title("From judgments to insights")
    st.caption("Trends, people and legal issues drawn from court judgments, each traceable to the source PDF.")

    # The four number cards. "Citations" counts both cited cases and cited Acts.
    keys = df["JUDGMENT_KEY"]
    judges = judge_counts(df)
    citations = len(for_judgments("case_citations", keys)) + len(for_judgments("legislation", keys))
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, df["CASE_NAME"].replace("", pd.NA).dropna().nunique(), "Cases")
    kpi(c2, len(df), "Judgments")
    kpi(c3, len(judges), "Judges")
    kpi(c4, citations, "Citations")
    st.write("")

    # First row of charts.
    left, right = st.columns(2)
    with left:
        st.subheader("Judgments over time")
        judgments_over_time(df)
    with right:
        st.subheader("Case categories")
        category_donut(df)

    # Second row of charts.
    left, right = st.columns(2)
    with left:
        st.subheader("Top 5 judges by number of judgments")
        if judges.empty:
            st.info("No judges recorded.")
        else:
            horizontal_bars(judges.head(5), "JUDGE_NAME", "Judgments", PURPLE)
    with right:
        st.subheader("Cases by location")
        loc = df.groupby("LOCATION").size().reset_index(name="Judgments")
        horizontal_bars(loc, "LOCATION", "Judgments", PINK)

    # Bottom row: the 5 newest judgments (click one to open it) and the insights.
    left, right = st.columns([2, 1])
    with left:
        st.subheader("Recent judgments")
        for _, row in df.head(5).iterrows():
            a, b, c, d = st.columns([1.2, 3, 1.8, 1.3])
            a.write(fmt_date(row["JUDGMENT_DATE"]))
            b.button(row["CASE_NAME"] or "Untitled", key=f"recent_{row['JUDGMENT_KEY']}",
                     on_click=open_case, args=(row["JUDGMENT_KEY"],))
            c.write(row["NEUTRAL_CITATION"])
            d.markdown(pill(row["CATEGORY"]), unsafe_allow_html=True)
    with right:
        st.subheader("💡 Key insights")
        key_insights(df, judges)


# ============================================================================
# Page 2: Case Explorer
# ============================================================================

def case_list(results):
    # The list of matching cases on the left, with sorting and page buttons.
    st.markdown(f"**Cases** ({len(results)} results)")
    sort = st.selectbox("Sort by", ["Judgment date (newest)", "Judgment date (oldest)", "Case name (A–Z)"])
    if sort == "Judgment date (oldest)":
        results = results.sort_values("JUDGMENT_DATE")
    elif sort == "Case name (A–Z)":
        results = results.sort_values("CASE_NAME")

    # Work out how many pages we need, and which slice of cases to show.
    # (-(-a // b) is a short way to divide and round up.)
    pages = max(1, -(-len(results) // PAGE_SIZE))
    page_no = min(st.session_state.get("page_no", 1), pages)
    start = (page_no - 1) * PAGE_SIZE

    # One button per case. The open case gets a small arrow in front of it.
    for _, row in results.iloc[start:start + PAGE_SIZE].iterrows():
        selected = row["JUDGMENT_KEY"] == st.session_state.get("selected_key")
        st.button(f"{'▶ ' if selected else ''}{row['CASE_NAME'] or 'Untitled'}", key=f"case_{row['JUDGMENT_KEY']}",
                  use_container_width=True, on_click=select_case, args=(row["JUDGMENT_KEY"],))
        st.markdown(f'<div class="muted">{row["NEUTRAL_CITATION"]} · {fmt_date(row["JUDGMENT_DATE"])} '
                    f'&nbsp;{status_pill(row)}</div>', unsafe_allow_html=True)
        st.write("")

    # Previous / Next buttons, only if there's more than one page.
    if pages > 1:
        prev_col, mid, next_col = st.columns([1, 2, 1])
        prev_col.button("Previous", disabled=page_no <= 1, on_click=set_page, args=(page_no - 1,))
        mid.markdown(f"<div style='text-align:center'>Page {page_no} of {pages}</div>", unsafe_allow_html=True)
        next_col.button("Next", disabled=page_no >= pages, on_click=set_page, args=(page_no + 1,))


def detail_rows(pairs):
    # A simple two-column table: label on the left, value on the right.
    # Empty values show as a dash. "$" is written as an HTML code (&#36;)
    # so it isn't mistaken for a maths formula inside the table.
    table = "".join(f"<tr><td class='muted' style='padding:4px 16px 4px 0'>{k}</td>"
                    f"<td style='padding:4px 0'>{str(v).replace('$', '&#36;') if v not in (None, '') else '—'}</td></tr>"
                    for k, v in pairs)
    st.markdown(f"<table>{table}</table>", unsafe_allow_html=True)


def page_label(page):
    # "page 4", or "page unknown" if the page number is missing.
    return f"page {int(page)}" if pd.notna(page) else "page unknown"


def case_details(row):
    # Everything about one judgment, on the right-hand side of the Case Explorer.
    key = row["JUDGMENT_KEY"]

    # Case name and citation, with its status badge.
    title_col, pill_col = st.columns([4, 1])
    title_col.header(row["CASE_NAME"] or "Untitled")
    title_col.markdown(f"**{row['NEUTRAL_CITATION']}**")
    pill_col.markdown(status_pill(row), unsafe_allow_html=True)

    # If the pipeline found signs of a suppression order or other publication
    # restriction, stop here. We show a notice and the basic court details,
    # but nothing from inside the judgment: no parties, outcome, quotes,
    # links or download. A person has to check the original first.
    if row["RESTRICTED"]:
        st.warning("🔒 This judgment may be subject to a suppression order or another publication "
                   "restriction, so its details are withheld. It needs to be checked by a person "
                   "against the original judgment before anything from it is shown.")
        detail_rows([
            ("Court", row["COURT"]),
            ("Judgment date", fmt_date(row["JUDGMENT_DATE"], "%d %B %Y")),
            ("Citation", row["NEUTRAL_CITATION"]),
            ("Status", "Details withheld pending review"),
        ])
        return

    # Load this judgment's details, each list in the order it appears in the judgment.
    one = pd.Series([key])
    cases_cited = for_judgments("case_citations", one).sort_values("REFERENCE_POSITION")
    acts = for_judgments("legislation", one).sort_values("REFERENCE_POSITION")
    evidence = for_judgments("evidence", one).sort_values("EVIDENCE_POSITION")
    quality = for_judgments("quality", one).sort_values("ISSUE_POSITION")
    issues = for_judgments("issues", one).sort_values("ISSUE_POSITION")

    # A quick sanity check: the year in the citation should match the year of
    # the judgment date. If not, one of them was probably extracted wrongly.
    cy = citation_year(row["NEUTRAL_CITATION"])
    if cy and pd.notna(row["JUDGMENT_DATE"]) and cy != row["JUDGMENT_DATE"].year:
        st.warning(f"Check the source: the citation says {cy} but the extracted judgment date is "
                   f"{fmt_date(row['JUDGMENT_DATE'], '%d %B %Y')}. One of them may be wrong.")

    tab_details, tab_legal, tab_source = st.tabs(["Case details", "Legal insights", "Source document"])

    # Tab 1: the basic facts and the outcome.
    with tab_details:
        detail_rows([
            ("Court", row["COURT"]),
            ("Location", row["LOCATION"]),
            ("Judgment date", fmt_date(row["JUDGMENT_DATE"], "%d %B %Y")),
            ("Case category", row["CATEGORY"]),
            ("Judges", row["JUDGES"]),
            ("Legal topics", row["TOPICS"]),
            ("Citation", row["NEUTRAL_CITATION"]),
            ("Source file", row["FILENAME"]),
            ("Pages", int(row["PAGE_COUNT"]) if pd.notna(row["PAGE_COUNT"]) else None),
        ])
        st.write("")
        st.markdown("#### 📄 Outcome")
        st.markdown(md_safe(row["OUTCOME"]) if row["OUTCOME"] else "No outcome extracted for this judgment.")

    # Tab 2: legal issues, plus the cases and Acts it cites, each with its page
    # number and the quote from the judgment as proof.
    with tab_legal:
        st.markdown("#### Legal issues")
        if issues.empty:
            st.caption("No legal issues recorded.")
        for _, i in issues.iterrows():
            st.markdown(f"- {md_safe(i['ISSUE_TEXT'])}")

        st.markdown("#### Cases cited")
        if cases_cited.empty:
            st.caption("No case citations recorded.")
        for _, c in cases_cited.iterrows():
            name = c["CITED_CASE_NAME"] if pd.notna(c["CITED_CASE_NAME"]) else ""
            # If the cited case is also one of our judgments, say so.
            in_data = " · in this dataset" if pd.notna(c["CITED_JUDGMENT_KEY"]) else ""
            st.markdown(f"- **{name} {c['CITATION'] or ''}**".replace("** ", "**") +
                        f" ({page_label(c['EVIDENCE_PAGE'])}{in_data})")
            if pd.notna(c["EVIDENCE_TEXT"]) and c["EVIDENCE_TEXT"]:
                st.caption(f"“{md_safe(c['EVIDENCE_TEXT'])}”")

        st.markdown("#### Legislation cited")
        if acts.empty:
            st.caption("No legislation recorded.")
        for _, a in acts.iterrows():
            section = f" s {a['SECTION']}" if pd.notna(a["SECTION"]) and a["SECTION"] else ""
            st.markdown(f"- **{a['ACT_NAME'] or 'Unnamed Act'}{section}** ({page_label(a['EVIDENCE_PAGE'])})")
            if pd.notna(a["EVIDENCE_TEXT"]) and a["EVIDENCE_TEXT"]:
                st.caption(f"“{md_safe(a['EVIDENCE_TEXT'])}”")

    # Tab 3: how much to trust this extraction - how many quotes were found in
    # the PDF, any problems the pipeline spotted, and the quotes themselves.
    with tab_source:
        total, ok = row["EVIDENCE_TOTAL"], row["EVIDENCE_VERIFIED"]
        detail_rows([
            ("Extraction status", row["EXTRACTION_STATUS"]),
            ("Evidence verified", f"{ok} of {total}" + (f" ({ok / total:.0%})" if total else "")),
            ("Needs human review", "Yes" if row["NEEDS_REVIEW"] else "No"),
            ("Verified for analytics", "Yes" if row["VERIFIED"] else "No"),
            ("Model", row["MODEL_ID"]),
            ("Extracted at", fmt_date(pd.to_datetime(row["EXTRACTED_AT"]), "%d %b %Y %H:%M")),
        ])
        if not quality.empty:
            st.markdown("#### ⚠️ Quality issues")
            for _, q in quality.iterrows():
                st.markdown(f"- **{q['ISSUE_TYPE'] or 'Issue'}:** {md_safe(q['ISSUE_TEXT'])}")
        st.markdown("#### Supporting evidence")
        if evidence.empty:
            st.caption("No evidence quotes recorded.")
        else:
            st.dataframe(evidence.rename(columns={"EVIDENCE_PAGE": "Page", "EVIDENCE_TEXT": "Quote from the judgment"})
                         [["Page", "Quote from the judgment"]], hide_index=True, use_container_width=True)

    # Quick actions under the tabs.
    st.markdown("#### Quick actions")
    a1, a2, a3, a4 = st.columns(4)

    # Only show a clickable link if it's a real web address. An S3 path
    # (s3://...) can't be opened in a browser, so we just show it as text.
    url = row["SOURCE_URL"]
    if url.startswith("http"):
        a1.markdown(f"[📄 View original PDF]({url})")
    else:
        a1.caption(f"Source: {url or row['FILENAME'] or 'not recorded'}")

    # st.code shows the text with a built-in copy button.
    with a2.expander("🔗 Copy link"):
        st.code(url or row["FILENAME"], language=None)
    with a3.expander("❝ Cite this case"):
        st.code(f"{row['CASE_NAME']} {row['NEUTRAL_CITATION']}".strip(), language=None)

    # Everything about this judgment, bundled into a JSON file to download.
    export = {
        "case": {k: row[k] for k in ("CASE_NAME", "NEUTRAL_CITATION", "COURT", "LOCATION", "CATEGORY",
                                     "JUDGES", "TOPICS", "OUTCOME", "FILENAME", "SOURCE_URL")},
        "judgment_date": fmt_date(row["JUDGMENT_DATE"], "%Y-%m-%d"),
        "legal_issues": issues["ISSUE_TEXT"].tolist(),
        "cases_cited": cases_cited.drop(columns="JUDGMENT_KEY").to_dict("records"),
        "legislation_cited": acts.drop(columns="JUDGMENT_KEY").to_dict("records"),
        "evidence": evidence.drop(columns="JUDGMENT_KEY").to_dict("records"),
    }
    a4.download_button("⬇️ Download details", data=json.dumps(export, indent=2, default=str),
                       file_name=f"{row['NEUTRAL_CITATION'] or key}.json".replace(" ", "_"),
                       mime="application/json")


def page_explorer():
    df = current_judgments()
    if df.empty:
        empty_state()

    # Title on the left, search box on the right.
    head, search_col = st.columns([3, 2])
    head.title("Case Explorer")
    head.caption("Search, filter and explore judgments.")
    term = search_col.text_input("Search", key="search", placeholder="Search cases, judges, topics…",
                                 label_visibility="collapsed")

    # The options for each dropdown, taken from the data itself.
    years = sorted({int(y) for y in df["YEAR"].dropna()}, reverse=True)
    judges = sorted({j.strip() for js in df["JUDGES"] for j in js.split(",") if j.strip()})
    categories = sorted(df["CATEGORY"].unique())
    locations = sorted(df["LOCATION"].unique())

    # Line the "Reset filters" button up with the bottom of the dropdowns.
    # Older Streamlit versions don't support that option, so we fall back
    # to a normal row if it isn't available.
    try:
        f1, f2, f3, f4, f5 = st.columns([1, 1.4, 1.2, 1.2, 0.8], vertical_alignment="bottom")
    except TypeError:
        f1, f2, f3, f4, f5 = st.columns([1, 1.4, 1.2, 1.2, 0.8])

    # Changing any filter sends the list back to page 1.
    year = f1.selectbox("Year", ["All"] + years, key="f_year", on_change=set_page, args=(1,))
    judge = f2.selectbox("Judge", ["All"] + judges, key="f_judge", on_change=set_page, args=(1,))
    category = f3.selectbox("Category", ["All"] + categories, key="f_category", on_change=set_page, args=(1,))
    location = f4.selectbox("Location", ["All"] + locations, key="f_location", on_change=set_page, args=(1,))
    f5.button("Reset filters", on_click=reset_filters, use_container_width=True)

    # Apply the search first, then each filter that isn't set to "All".
    results = apply_search(df, term)
    if year != "All":
        results = results[results["YEAR"] == year]
    if judge != "All":
        results = results[results["JUDGES"].str.contains(judge, regex=False)]
    if category != "All":
        results = results[results["CATEGORY"] == category]
    if location != "All":
        results = results[results["LOCATION"] == location]

    # Case list on the left (1 part), details on the right (2 parts).
    list_col, detail_col = st.columns([1, 2])
    with list_col:
        if results.empty:
            st.info("No judgments match these filters. Clear the search or reset filters.")
        else:
            case_list(results)
    with detail_col:
        # Show the case the user picked. If they haven't picked one yet,
        # show the first case in the list so the page is never empty.
        match = df[df["JUDGMENT_KEY"] == st.session_state.get("selected_key")]
        if match.empty and not results.empty:
            match = results.head(1)
        if match.empty:
            st.info("Select a case to see its details.")
        else:
            case_details(match.iloc[0])

    st.markdown('<div class="note">ℹ️ Sourced from published judgments of the Courts of New Zealand. '
                'Refer to the original judgment for full details.</div>', unsafe_allow_html=True)


# ============================================================================
# Page 3: Insights
# ============================================================================

def page_insights():
    df = current_judgments()
    if df.empty:
        empty_state()
    keys = df["JUDGMENT_KEY"]
    st.title("Insights")
    st.caption("What the judgments show, and how far to trust the extracted data.")

    # Most common topics and Acts. We count judgments, not mentions, so one
    # judgment citing the same Act ten times still counts once.
    left, right = st.columns(2)
    with left:
        st.subheader("Most common legal topics")
        topics = for_judgments("topics", keys)
        if topics.empty:
            st.info("No topics recorded.")
        else:
            t = topics.groupby("TOPIC_NAME")["JUDGMENT_KEY"].nunique().reset_index(name="Judgments")
            horizontal_bars(t.sort_values("Judgments", ascending=False).head(10), "TOPIC_NAME", "Judgments", BLUE, 300)
    with right:
        st.subheader("Most cited legislation")
        acts = for_judgments("legislation", keys)
        if acts.empty:
            st.info("No legislation recorded.")
        else:
            a = acts.fillna({"ACT_NAME": "Unnamed Act"}).groupby("ACT_NAME")["JUDGMENT_KEY"] \
                    .nunique().reset_index(name="Judgments")
            horizontal_bars(a.sort_values("Judgments", ascending=False).head(10), "ACT_NAME", "Judgments", PURPLE, 300)

    # Earlier cases that our judgments refer to most often (top 10).
    st.subheader("Most cited cases")
    cited = for_judgments("case_citations", keys)
    if cited.empty:
        st.info("No case citations recorded.")
    else:
        cited = cited.assign(CASE=(cited["CITED_CASE_NAME"].fillna("") + " " + cited["CITATION"].fillna("")).str.strip())
        c = cited.groupby("CASE")["JUDGMENT_KEY"].nunique().reset_index(name="Citing judgments")
        horizontal_bars(c.sort_values("Citing judgments", ascending=False).head(10), "CASE", "Citing judgments", PINK, 300)

    # How trustworthy is the AI extraction? These numbers use every extracted
    # judgment, not just the ones on screen, so the picture is complete.
    st.subheader("AI extraction quality")
    all_j = load_judgments_enriched()
    total, verified = int(all_j["EVIDENCE_TOTAL"].sum()), int(all_j["EVIDENCE_VERIFIED"].sum())
    c1, c2, c3, c4 = st.columns(4)
    kpi(c1, len(all_j), "Judgments extracted")
    kpi(c2, int(all_j["VERIFIED"].sum()), "Verified for analytics")
    kpi(c3, int(all_j["NEEDS_REVIEW"].sum()), "Flagged for review")
    c4.markdown(f'<div class="kpi"><div class="num">{(verified / total if total else 0):.0%}</div>'
                f'<div class="lbl">Evidence quotes verified</div></div>', unsafe_allow_html=True)

    # Be open about what's included, and say how many judgments were flagged
    # for a possible publication restriction.
    flagged = int(all_j["RESTRICTED"].sum())
    st.caption("These figures cover every extracted judgment, including those not yet verified."
               + (f" {flagged} judgment(s) were flagged for a possible publication restriction; "
                  "they are listed in the Case Explorer but their details are locked." if flagged else ""))
    st.write("")

    left, right = st.columns(2)
    with left:
        # For each judgment: how many supporting quotes were found in the PDF
        # (green) and how many weren't (amber).
        st.markdown("**Evidence verified per judgment**")
        ev = all_j[["CASE_NAME", "EVIDENCE_VERIFIED", "EVIDENCE_TOTAL"]].copy()
        ev["Unverified"] = (ev["EVIDENCE_TOTAL"] - ev["EVIDENCE_VERIFIED"]).clip(lower=0)
        # Reshape into one row per judgment per status, which is the layout a
        # stacked bar chart needs.
        long = ev.rename(columns={"EVIDENCE_VERIFIED": "Verified"}) \
                 .melt(id_vars="CASE_NAME", value_vars=["Verified", "Unverified"], var_name="Status", value_name="Quotes")
        st.altair_chart(alt.Chart(long).mark_bar().encode(
            y=alt.Y("CASE_NAME:N", title=None, axis=alt.Axis(labelLimit=260)),
            x=alt.X("Quotes:Q", title="Evidence quotes", axis=alt.Axis(format="d", tickMinStep=1)),
            color=alt.Color("Status:N", scale=alt.Scale(domain=["Verified", "Unverified"], range=[GREEN, AMBER])),
            tooltip=["CASE_NAME", "Status", "Quotes"],
        ).properties(height=max(200, 24 * len(ev))), use_container_width=True)
    with right:
        # The kinds of problems the pipeline caught, and how many of each.
        st.markdown("**Quality issues by type**")
        q = safe_load("quality")
        if q.empty:
            st.caption("No quality issues recorded.")
        else:
            qc = q.fillna({"ISSUE_TYPE": "Other"}).groupby("ISSUE_TYPE").size().reset_index(name="Issues")
            horizontal_bars(qc, "ISSUE_TYPE", "Issues", AMBER)

        # Where each judgment is in the process, e.g. ACCEPTED or REVIEW_REQUIRED.
        st.markdown("**Extraction status**")
        s = all_j.assign(STATUS=all_j["EXTRACTION_STATUS"].replace("", "Unknown")) \
                 .groupby("STATUS").size().reset_index(name="Judgments")
        horizontal_bars(s, "STATUS", "Judgments", BLUE, 160)


# ============================================================================
# Sidebar and page switching
# ============================================================================

PAGES = {"Overview": page_overview, "Case Explorer": page_explorer, "Insights": page_insights}

with st.sidebar:
    st.markdown("## ⚖️ CourtLens")
    st.markdown("New Zealand court insights")
    # The page menu. key="nav" lets buttons elsewhere switch pages too.
    choice = st.radio("Navigate", list(PAGES), key="nav", label_visibility="collapsed")
    st.write("")
    # Unticked by default, so every judgment is shown.
    # Tick it to see only judgments whose evidence passed verification.
    st.checkbox("Verified judgments only", value=False, key="verified_only",
                help="Show only judgments whose extracted evidence passed verification.")
    st.caption("Data for learning and research purposes only.")

# Draw whichever page is selected in the menu.
PAGES[choice]()
