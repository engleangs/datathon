"""Test-only stand-in for Snowflake: a fake session returning sample rows shaped like
DATATHON_TEST.ANALYTICS_ANALYTICS. Nothing here is shipped to Snowflake or shown to users."""
import datetime as dt
import sys
import types

import pandas as pd

J = []
for i in range(1, 11):
    J.append(dict(
        JUDGMENT_KEY=f"j{i}", DOCUMENT_ID=f"d{i}", CASE_NAME=f"TEST CASE {i} v R" if i % 3 else f"ALPHA {i} v BETA",
        NEUTRAL_CITATION=f"[2026] NZSC {100 + i}" if i % 2 else f"[2022] NZDC {700 + i}",
        JUDGMENT_DATE=dt.date(2026 if i % 2 else 2022, 1 + i % 9, 1 + i),
        OUTCOME="Fine of $33,500 and costs of $130." if i % 2 else None, EXTRACTION_STATUS="complete",
        AGENT_NEEDS_HUMAN_REVIEW=(i == 4), IS_VERIFIED_FOR_DEFAULT_ANALYTICS=(i != 10),
        EVIDENCE_VERIFIED=5 if i % 4 else 3, EVIDENCE_TOTAL=5, MODEL_ID="bedrock-model",
        EXTRACTED_AT=dt.datetime(2026, 9, 24, 12, i),
        COURT_NAME="SUPREME COURT OF NEW ZEALAND" if i % 2 else "DISTRICT COURT AT AUCKLAND",
        CASE_CATEGORY_NAME=["Criminal", "Civil", None][i % 3],
        FILENAME=f"{i}.pdf", SOURCE_URL=f"https://example.org/{i}.pdf" if i % 2 else f"s3://bucket/{i}.pdf",
        PAGE_COUNT=5))
# an older extraction of document d1 that must be ignored (latest wins)
J.append(dict(J[0], JUDGMENT_KEY="j1_old", CASE_NAME="OLD", EXTRACTED_AT=dt.datetime(2026, 9, 1)))

DATA = {
    "FCT_JUDGMENT": pd.DataFrame(J),
    "BRIDGE_JUDGMENT_JUDGE": pd.DataFrame(
        [dict(JUDGMENT_KEY=f"j{i}", JUDGE_POSITION=p, JUDGE_NAME=n)
         for i in range(1, 11) for p, n in enumerate(["GLAZEBROOK J", "DA KIRKPATRICK"][: 1 + i % 2])]),
    "BRIDGE_JUDGMENT_TOPIC": pd.DataFrame(
        [dict(JUDGMENT_KEY=f"j{i}", TOPIC_POSITION=1, TOPIC_NAME=["Sentencing", "Estates"][i % 2]) for i in range(1, 11)]),
    "FCT_JUDGMENT_LEGAL_ISSUE": pd.DataFrame([dict(JUDGMENT_KEY="j1", ISSUE_POSITION=1, ISSUE_TEXT="Parity in sentencing")]),
    "FCT_CASE_CITATION": pd.DataFrame([
        dict(JUDGMENT_KEY="j1", CITED_CASE_NAME=None, CITATION="Henderson v R [2017] NZCA 605", CITED_JUDGMENT_KEY=None,
             REFERENCE_POSITION=1, EVIDENCE_PAGE=4, EVIDENCE_TEXT="1 Henderson v R [2017] NZCA 605."),
        dict(JUDGMENT_KEY="j3", CITED_CASE_NAME="Test Case 1 v R", CITATION="[2026] NZSC 101", CITED_JUDGMENT_KEY="j1",
             REFERENCE_POSITION=1, EVIDENCE_PAGE=None, EVIDENCE_TEXT=None)]),
    "FCT_LEGISLATION_CITATION": pd.DataFrame([
        dict(JUDGMENT_KEY="j1", ACT_NAME="Customs and Excise Act 2018", SECTION="371", REFERENCE_POSITION=1,
             EVIDENCE_PAGE=3, EVIDENCE_TEXT="seven charges under s 371")]),
    "FCT_JUDGMENT_EVIDENCE": pd.DataFrame([dict(JUDGMENT_KEY="j1", EVIDENCE_POSITION=1, EVIDENCE_PAGE=2,
                                                EVIDENCE_TEXT="You are married to Mr Hu.")]),
    "FCT_JUDGMENT_QUALITY_ISSUE": pd.DataFrame([
        dict(JUDGMENT_KEY="j4", ISSUE_TYPE="missing_reference", ISSUE_POSITION=1, ISSUE_TEXT="Cited case not found"),
        dict(JUDGMENT_KEY="j9", ISSUE_TYPE="PUBLICATION_MARKER_FOUND", ISSUE_POSITION=1, ISSUE_TEXT="Suppression order")]),
}


class Result:
    def __init__(self, df):
        self.df = df

    def to_pandas(self):
        return self.df.copy()


class Session:
    def use_warehouse(self, name):
        assert name == "DTH_WH"

    def sql(self, q):
        q = q.upper()
        if "FROM DATATHON_TEST.ANALYTICS_ANALYTICS.FCT_JUDGMENT\n" in q or "FCT_JUDGMENT\n            QUALIFY" in q:
            df = DATA["FCT_JUDGMENT"]
            return Result(df.sort_values("EXTRACTED_AT").drop_duplicates("DOCUMENT_ID", keep="last"))
        for name in ("BRIDGE_JUDGMENT_JUDGE", "BRIDGE_JUDGMENT_TOPIC", "FCT_JUDGMENT_LEGAL_ISSUE", "FCT_CASE_CITATION",
                     "FCT_LEGISLATION_CITATION", "FCT_JUDGMENT_EVIDENCE", "FCT_JUDGMENT_QUALITY_ISSUE"):
            if f".{name}" in q:
                return Result(DATA[name])
        raise ValueError(q)


ctx = types.ModuleType("snowflake.snowpark.context")
ctx.get_active_session = lambda: Session()
for name in ("snowflake", "snowflake.snowpark"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["snowflake.snowpark.context"] = ctx
