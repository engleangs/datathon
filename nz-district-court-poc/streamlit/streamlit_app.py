"""District Court Insights: Streamlit in Snowflake app.

Deploy: Snowsight > Projects > Streamlit > + Streamlit App
        Role NZDC_DEV_TRANSFORMER, database NZDC_DEV, schema MARTS, warehouse NZDC_DEV_WH.
        Paste this file. Then: GRANT USAGE ON STREAMLIT NZDC_DEV.MARTS.<app> TO ROLE NZDC_DEV_ANALYST;

Case names are masked by the OPS.MASK_PARTY_NAME policy ("R v [withheld]").
The app runs with its owner's role, so viewers never see party names.
"""

import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="District Court Insights", layout="wide")
session = get_active_session()
DB = "NZDC_DEV"
REFORM = "29 June 2025"


@st.cache_data(ttl=600)
def q(sql: str) -> pd.DataFrame:
    df = session.sql(sql).to_pandas()
    df.columns = [c.lower() for c in df.columns]
    return df


st.title("District Court Insights")
st.caption("District Court of New Zealand decisions turned into data with Snowflake Cortex and Amazon Bedrock. "
           "AI output: check the decision before you rely on any number.")

f = q(f"select * from {DB}.MARTS.FCT_DC_DECISIONS")
if f.empty:
    st.info("No decisions yet. Upload PDFs and run CALL NZDC_DEV.RAW.PROCESS_NEW_DECISIONS();")
    st.stop()

with st.sidebar:
    st.header("Filters")
    reg = st.multiselect("Registry", sorted(f["registry"].dropna().unique()))
    ctype = st.multiselect("Case type", sorted(f["case_type"].dropna().unique()))
    off = st.multiselect("Offence type", sorted(f["primary_offence_type"].dropna().unique()))
    review_only = st.checkbox("Only rows that need review")
if reg:
    f = f[f["registry"].isin(reg)]
if ctype:
    f = f[f["case_type"].isin(ctype)]
if off:
    f = f[f["primary_offence_type"].isin(off)]
if review_only:
    f = f[f["needs_review"]]

sent = f[(f["case_type"] == "criminal") & (f["document_type"] == "sentencing")]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Decisions", len(f))
c2.metric("Sentencing notes", len(sent))
c3.metric("Registries", f["registry"].nunique())
c4.metric("Home detention outcomes", int((sent["sentence_type"] == "home detention").sum()))
c5.metric("Need review", int(f["needs_review"].sum()))

tab1, tab2, tab3, tab4 = st.tabs(["Sentencing reform", "Sentencing ladder", "Courts and Acts", "Pipeline health"])

with tab1:
    st.subheader(f"Discounts before and after {REFORM}")
    st.caption("Sentencing (Reform) Amendment Act 2025: personal mitigation capped at 40%, guilty plea at most 25%. "
               "A small sample shows the method, not a finding about the law.")
    agg = q(f"select * from {DB}.MARTS.AGG_SENTENCING_REFORM where offence_type = 'all' order by reform_period")
    st.dataframe(agg, hide_index=True, use_container_width=True)
    if len(sent):
        left, right = st.columns(2)
        with left:
            st.markdown("**Personal mitigation % per decision**")
            st.bar_chart(sent.pivot_table(index="neutral_citation", columns="reform_period",
                                          values="personal_mitigation_percent", aggfunc="mean"))
        with right:
            st.markdown("**Sentence types**")
            st.bar_chart(sent.pivot_table(index="sentence_type", columns="reform_period",
                                          values="relative_path", aggfunc="count", fill_value=0))
        over = sent[sent["over_mitigation_cap"].fillna(False) & (sent["reform_period"] == "after reform")]
        if len(over):
            st.warning(f"{len(over)} decision(s) after the reform show personal mitigation over 40%. "
                       "Check them: a misread, or the judge found the cap manifestly unjust.")

with tab2:
    st.subheader("From starting point to end sentence")
    if sent.empty:
        st.write("No sentencing notes in this filter.")
    else:
        pick = st.selectbox("Decision", sent["relative_path"].tolist(),
                            format_func=lambda p: f"{sent.loc[sent.relative_path == p, 'neutral_citation'].iloc[0]} "
                                                  f"({sent.loc[sent.relative_path == p, 'case_name'].iloc[0]})")
        row = sent[sent["relative_path"] == pick].iloc[0]
        a, b = st.columns([1, 2])
        with a:
            st.markdown(f"**{row['neutral_citation']}** · {row['registry']} · {row['judgment_date']}")
            st.markdown(f"**Lead offence:** {row['lead_offence'] or 'n/a'}")
            st.markdown(f"**Starting point:** {row['starting_point_months']} months")
            st.markdown(f"**End sentence:** {row['end_sentence_months']} months ({row['sentence_type']})")
            st.markdown(f"**Guilty plea:** {row['guilty_plea_percent']}% · "
                        f"**Personal mitigation:** {row['personal_mitigation_percent']}%")
            gap = row["arithmetic_gap_months"]
            if pd.notna(gap) and abs(gap) > 1:
                st.error(f"Arithmetic check: the steps do not add up (gap {gap} months).")
            st.markdown(f"**Summary (Cortex):** {row['summary']}")
        with b:
            ladder = q(f"""select step, factor, category, direction, percent, months
                           from {DB}.MARTS.FCT_SENTENCING_ADJUSTMENTS
                           where relative_path = '{pick.replace("'", "''")}' order by step""")
            st.dataframe(ladder, hide_index=True, use_container_width=True)

with tab3:
    left, right = st.columns(2)
    with left:
        st.markdown("**Decisions by registry**")
        st.bar_chart(f.groupby("registry").size().sort_values(ascending=False).head(15))
    with right:
        st.markdown("**Most cited Acts**")
        acts = q(f"""select statute, count(distinct relative_path) as decisions
                     from {DB}.MARTS.BRIDGE_DC_STATUTES group by 1 order by 2 desc limit 15""")
        st.bar_chart(acts.set_index("statute"))
    st.markdown("**Offence types (criminal)**")
    st.bar_chart(f[f["case_type"] == "criminal"].groupby("primary_offence_type").size())

with tab4:
    try:
        runs = q(f"select * from {DB}.OPS.V_PIPELINE_HEALTH")
        st.dataframe(runs, hide_index=True, use_container_width=True)
    except Exception:
        st.write("Run sql/03_monitoring.sql to create the monitoring views.")
    try:
        acc = q(f"select * from {DB}.MARTS.EVAL_EXTRACTION_ACCURACY")
        st.markdown("**Extraction accuracy against hand-labelled decisions**")
        st.dataframe(acc, hide_index=True, use_container_width=True)
    except Exception:
        st.write("Fill in dbt/seeds/gold_labels.csv, then run dbt seed and dbt run to see accuracy.")
