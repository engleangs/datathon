# CourtLens dashboard

A Streamlit in Snowflake app that shows the court judgments our pipeline has
extracted. It reads the dbt models in `DATATHON_TEST.ANALYTICS_ANALYTICS` and
never writes back to Snowflake.

## Pages

- **Overview**: headline numbers, judgments over time, case categories,
  top judges, cases by location, recent judgments and key insights.
- **Case Explorer**: search and filter judgments, then open one to see its
  details, the cases and Acts it cites, and the quotes from the PDF that
  back up each extracted value.
- **Insights**: most common topics, most cited legislation and cases, and how
  reliable the AI extraction is (verified quotes, review flags, quality issues).

All judgments are shown by default, each with a badge: Verified, Unverified,
Needs review, or Check publication restriction. The sidebar checkbox narrows
the view to verified judgments only.

Judgments where the pipeline found signs of a suppression order or another
publication restriction stay in the list, but their details are locked:
clicking one shows only a notice with the court, date and citation. Nothing
from inside the judgment (parties, outcome, quotes, download) is shown until
a person has checked the original.

## Where it runs

Deployed from a Snowflake Workspace as a Streamlit app:

| Setting | Value |
|---|---|
| App location | `DATATHON_TEST.COURTLENS` |
| Query warehouse | `DTH_WH` |
| Runs as role | `SYSADMIN` |
| Reads data from | `DATATHON_TEST.ANALYTICS_ANALYTICS` |

To update the live app: edit `streamlit_app.py` in the Workspace, click
**Run** to preview, then **Deploy**. Copy the same file into this folder and
commit it, so GitHub and Snowflake stay the same.

## Views it reads

| Panel | Views |
|---|---|
| Every page (one row per judgment, latest extraction per document) | `FCT_JUDGMENT`, `DIM_COURT`, `DIM_CASE_CATEGORY`, `DIM_SOURCE_DOCUMENT` |
| Judges | `BRIDGE_JUDGMENT_JUDGE`, `DIM_JUDGE` |
| Topics | `BRIDGE_JUDGMENT_TOPIC`, `DIM_TOPIC` |
| Legal issues | `FCT_JUDGMENT_LEGAL_ISSUE` |
| Cases cited | `FCT_CASE_CITATION`, `DIM_CITED_CASE` |
| Legislation cited | `FCT_LEGISLATION_CITATION`, `DIM_LEGISLATION` |
| Evidence and quality | `FCT_JUDGMENT_EVIDENCE`, `FCT_JUDGMENT_QUALITY_ISSUE` |

## Tests

The tests run the whole app without Snowflake, using sample rows from
`tests/fake_snowflake.py`. Run them on their own, not together with the
repo's main `tests` folder, because the fake Snowflake module would clash
with tests that use the real one.

```
pip install -r dashboard/requirements-dev.txt
pytest dashboard/tests
```
