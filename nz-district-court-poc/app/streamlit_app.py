"""District Court Decision Intake: a local Streamlit app.

Upload District Court of New Zealand decision PDFs -> read the text layer (no OCR)
-> exclusion gate (Youth Court / Family Court) -> rule-based fields
-> review and fix -> download CSV / JSONL, and optionally send to S3
for the Snowflake Cortex + Bedrock pipeline.

Run:
    python -m pip install -r app/requirements.txt
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import re

import pandas as pd
import streamlit as st

from pdf_extract import MIN_CHARS_PER_PAGE, MITIGATION_CAP_PCT, REFORM_DATE, DcResult, read_pdf

MAX_MB = 100  # same limit as Snowflake AI functions

st.set_page_config(page_title="District Court Decision Intake", layout="wide")


@st.cache_data(show_spinner=False, max_entries=500)
def process(data: bytes, name: str) -> DcResult:
    return read_pdf(data, name)


def s3_key(name: str) -> str:
    stem, _, _ = name.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")
    return f"judgments/{stem}.pdf"


def fmt_months(m: float | None) -> str:
    if m is None:
        return "n/a"
    y, mo = divmod(round(m, 2), 12)
    parts = ([f"{int(y)} yr"] if y else []) + ([f"{mo:g} mo"] if mo else [])
    return " ".join(parts) or "0 mo"


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Settings")
    preview_chars = st.slider("Text preview length", 500, 10000, 2500, step=500)

    st.divider()
    st.subheader("Send to S3 (optional)")
    bucket = st.text_input("Bucket", placeholder="nzdc-dev-judgments-123456789012",
                           help="terraform -chdir=terraform output -raw s3_bucket")
    st.caption("Uses your normal AWS credentials (AWS_PROFILE or env vars). "
               "Excluded, scanned and broken files are never sent.")

# ------------------------------------------------------------------ main
st.title("District Court Decision Intake")
st.caption("Reads the PDF text layer only (no OCR). Youth Court and Family Court decisions are "
           "excluded and their text is dropped. Fields come from simple rules: check them before "
           "you rely on them.")

files = st.file_uploader("Drop District Court decision PDFs here", type=["pdf"], accept_multiple_files=True)

if not files:
    st.info("Upload one or more PDFs to start. Download them by hand from districtcourts.govt.nz. "
            "Do not use NZLII or any scraper.")
    st.stop()

results: list[DcResult] = []
too_big: list[str] = []
progress = st.progress(0.0, text="Reading PDFs...")
for i, f in enumerate(files, start=1):
    if f.size > MAX_MB * 1024 * 1024:
        too_big.append(f.name)
    else:
        results.append(process(f.getvalue(), f.name))
    progress.progress(i / len(files), text=f"Read {i} of {len(files)}")
progress.empty()

seen: dict[str, str] = {}
dupes = []
for r in results:
    if r.sha256 in seen:
        dupes.append(f"{r.file_name} = {seen[r.sha256]}")
    else:
        seen[r.sha256] = r.file_name

ok = [r for r in results if r.is_usable]
excluded = [r for r in results if r.excluded_reason]
ocr = [r for r in results if r.needs_ocr]
bad = [r for r in results if r.error]

# ------------------------------------------------------------------ KPIs
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Files", len(files))
c2.metric("Usable", len(ok))
c3.metric("Excluded", len(excluded))
c4.metric("Need OCR", len(ocr))
c5.metric("Errors", len(bad) + len(too_big))
c6.metric("Sentencing notes", sum(r.document_type == "sentencing" for r in ok))

for name in too_big:
    st.error(f"{name}: larger than {MAX_MB} MB. Skipped.")
for r in bad:
    st.error(f"{r.file_name}: {r.error}")
for r in excluded:
    st.warning(f"{r.file_name}: EXCLUDED ({r.excluded_reason.replace('_', ' ')}, {r.neutral_citation or 'no citation'}). "
               "Text dropped. This file will not be processed or uploaded.")
for r in ocr:
    st.warning(f"{r.file_name}: no text layer. It is a scanned PDF and needs OCR. Skipped.")
for r in ok:
    if r.partly_scanned:
        st.warning(f"{r.file_name}: {r.page_count - r.text_pages} of {r.page_count} pages have no text "
                   f"(under {MIN_CHARS_PER_PAGE} characters). Those pages are missing.")
for d in dupes:
    st.warning(f"Duplicate content: {d}")

if not ok:
    st.stop()

# ------------------------------------------------------------------ table
st.subheader("Extracted fields")
df = pd.DataFrame([r.summary_row() for r in ok])
cols = ["file_name", "neutral_citation", "registry", "file_number", "case_type", "judge",
        "judgment_date", "document_type", "reform_period", "starting_point_months",
        "end_sentence_months", "sentence_type", "home_detention_months", "guilty_plea_pct",
        "personal_mitigation_pct", "reparation_nzd", "amount_claimed_nzd", "amount_awarded_nzd",
        "mentions_suppression", "sections_cited", "page_count"]
df = df[[c for c in cols if c in df.columns]]

edited = st.data_editor(
    df, width="stretch", hide_index=True, num_rows="fixed",
    disabled=["file_name", "page_count", "reform_period"],
    column_config={
        "mentions_suppression": st.column_config.CheckboxColumn("suppression note?"),
        "case_type": st.column_config.SelectboxColumn(options=["criminal", "civil", None]),
        "document_type": st.column_config.SelectboxColumn(
            options=["sentencing", "reserved judgment", "oral judgment", "appeal", "other", None]),
        "sentence_type": st.column_config.SelectboxColumn(
            options=["imprisonment", "home detention", "community detention", "intensive supervision",
                     "supervision", "community work", "fine", "discharge without conviction",
                     "conviction and discharge", "other", None]),
        "guilty_plea_pct": st.column_config.NumberColumn("guilty plea %", min_value=0, max_value=25),
        "personal_mitigation_pct": st.column_config.NumberColumn("personal mitigation %"),
        "reparation_nzd": st.column_config.NumberColumn("reparation $", format="$%.2f"),
    },
    key="fields_editor",
)

key_fields = ["neutral_citation", "registry", "judgment_date", "document_type"]
st.caption("Fields found: " + " · ".join(f"{k} {int(edited[k].notna().sum())}/{len(edited)}" for k in key_fields))

# ------------------------------------------------------------------ reform view
sent = edited[(edited["case_type"] == "criminal") & (edited["document_type"] == "sentencing")]
if len(sent):
    st.subheader("Sentencing discounts: before and after the reform")
    st.caption(f"Sentencing (Reform) Amendment Act 2025, in force {REFORM_DATE:%d %B %Y}: personal mitigation "
               f"capped at {MITIGATION_CAP_PCT}%, guilty plea at most 25%. A small sample shows the method, "
               "not a finding about the law.")
    by_period = (sent.groupby("reform_period", dropna=False)
                     .agg(decisions=("file_name", "count"),
                          avg_guilty_plea_pct=("guilty_plea_pct", "mean"),
                          avg_personal_mitigation_pct=("personal_mitigation_pct", "mean"),
                          over_cap=("personal_mitigation_pct", lambda s: int((s > MITIGATION_CAP_PCT).sum())))
                     .reset_index())
    st.dataframe(by_period, hide_index=True, width="stretch")
    over = sent[(sent["personal_mitigation_pct"] > MITIGATION_CAP_PCT) & (sent["reform_period"] == "after reform")]
    for _, row in over.iterrows():
        st.error(f"{row['file_name']}: personal mitigation {row['personal_mitigation_pct']:g}% after the reform. "
                 "Check the decision: either the rules misread it, or the judge found the cap manifestly unjust.")

# ------------------------------------------------------------------ downloads
d1, d2 = st.columns(2)
d1.download_button("Download fields (CSV)", edited.to_csv(index=False).encode(),
                   "dc_decision_fields.csv", "text/csv", width="stretch")
jsonl = "\n".join(
    json.dumps({"file_name": r.file_name, "sha256": r.sha256,
                "pages": [{"index": i, "content": p} for i, p in enumerate(r.pages)]},
               ensure_ascii=False)
    for r in ok
)
d2.download_button("Download full text (JSONL, one line per PDF)", jsonl.encode(),
                   "dc_decision_text.jsonl", "application/json", width="stretch")

# ------------------------------------------------------------------ detail
st.subheader("Decision detail")
pick = st.selectbox("Choose a file", [r.file_name for r in ok])
r = next(x for x in ok if x.file_name == pick)

a, b = st.columns([1, 2])
with a:
    st.markdown(f"**{r.neutral_citation or 'No citation found'}**")
    st.markdown(f"**Registry:** {r.registry or 'n/a'}  \n**File no.:** {r.file_number or 'n/a'}  \n"
                f"**Type:** {r.case_type or 'n/a'} · {r.document_type or 'n/a'}")
    st.markdown(f"**Judge:** {r.judge or 'n/a'}  \n**Hearing:** {r.hearing_date or 'n/a'}  \n"
                f"**Judgment:** {r.judgment_date or 'n/a'} ({r.reform_period or 'date unknown'})")
    if r.publication_note:
        st.error(f"Publication note: {r.publication_note}")
    elif r.mentions_suppression:
        st.error("Mentions suppression. Check before you use this file.")

    if r.case_type == "criminal":
        st.markdown("**Sentencing (rules)**")
        ladder = pd.DataFrame([
            {"step": "Starting point", "value": fmt_months(r.starting_point_months), "as written": r.starting_point},
            {"step": "Guilty plea discount", "value": f"{r.guilty_plea_pct:g}%" if r.guilty_plea_pct is not None else "n/a", "as written": ""},
            {"step": "Personal mitigation (sum)", "value": f"{r.personal_mitigation_pct:g}%" if r.personal_mitigation_pct is not None else "n/a", "as written": ""},
            {"step": "End sentence", "value": fmt_months(r.end_sentence_months), "as written": r.end_sentence},
            {"step": "Home detention", "value": fmt_months(r.home_detention_months) if r.home_detention_months else "n/a", "as written": ""},
            {"step": "Sentence type", "value": r.sentence_type or "n/a", "as written": ""},
            {"step": "Reparation", "value": f"${r.reparation_nzd:,.2f}" if r.reparation_nzd else "n/a", "as written": ""},
        ])
        st.dataframe(ladder, hide_index=True, width="stretch")
        st.caption("The Bedrock step in the pipeline builds the full ladder: every uplift and discount, in order.")
    elif r.case_type == "civil":
        st.markdown(f"**Claimed:** {f'${r.amount_claimed_nzd:,.2f}' if r.amount_claimed_nzd else 'n/a'}  \n"
                    f"**Awarded:** {f'${r.amount_awarded_nzd:,.2f}' if r.amount_awarded_nzd else 'n/a'}")

    with st.expander(f"Sections cited ({len(r.sections_cited)})"):
        st.write(r.sections_cited or "None found")
    with st.expander(f"Acts cited ({len(r.statutes_cited)})"):
        st.write(r.statutes_cited or "None found")
with b:
    page_no = st.number_input("Page", 1, max(r.page_count, 1), 1)
    text = r.pages[page_no - 1] if r.pages else ""
    st.caption(f"{len(text):,} characters on this page")
    st.text_area("Page text", text[:preview_chars], height=460, label_visibility="collapsed")

# ------------------------------------------------------------------ S3 upload
st.subheader("Send to the pipeline")
if not bucket:
    st.caption("Enter a bucket name in the sidebar to turn this on.")
else:
    usable_names = {x.file_name for x in ok}
    sendable = [f for f in files if f.name in usable_names]
    st.write(f"{len(sendable)} usable PDFs will go to `s3://{bucket}/judgments/`.")
    if st.button("Upload to S3", type="primary", disabled=not sendable):
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError:
            st.error("boto3 is not installed. Run: python -m pip install boto3")
            st.stop()
        s3 = boto3.client("s3")
        done, failed = 0, []
        bar = st.progress(0.0)
        for i, f in enumerate(sendable, start=1):
            try:
                s3.put_object(Bucket=bucket, Key=s3_key(f.name), Body=f.getvalue(),
                              ContentType="application/pdf", ServerSideEncryption="AES256")
                done += 1
            except (BotoCoreError, ClientError) as exc:
                failed.append(f"{f.name}: {exc}")
            bar.progress(i / len(sendable))
        st.success(f"Uploaded {done} file(s). Next, in Snowflake: CALL NZDC_DEV.RAW.PROCESS_NEW_DECISIONS();")
        for msg in failed:
            st.error(msg)
