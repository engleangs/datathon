"""Streamlit app: PDF in, CSV out, same columns for every PDF.

Run:  streamlit run app.py
"""
import io
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from schema import COLUMNS, pdf_to_row, rows_to_csv

st.set_page_config(page_title="NZ District Court PDF to CSV", layout="wide")
st.title("NZ District Court PDF to CSV")
st.caption(
    "Every PDF gives one row with the same columns: " + ", ".join(COLUMNS) + ". "
    "The last three columns are filled only for sentencing notes. For other documents they are empty."
)


@st.cache_data(show_spinner=False)
def convert(name: str, data: bytes) -> dict:
    return pdf_to_row(data, name)


files = st.file_uploader("PDF files", type=["pdf"], accept_multiple_files=True)

if not files:
    st.info("Upload one or more PDFs to start.")
    st.stop()

rows = []
bar = st.progress(0.0, text="Reading PDFs...")
for i, f in enumerate(files, 1):
    rows.append(convert(f.name, f.getvalue()))
    bar.progress(i / len(files), text=f"Read {i} of {len(files)}")
bar.empty()

st.dataframe(pd.DataFrame(rows, columns=COLUMNS), use_container_width=True, hide_index=True)

c1, c2 = st.columns(2)
c1.download_button(
    "Download one CSV (all PDFs)",
    rows_to_csv(rows).encode("utf-8"),
    "district_court.csv", "text/csv",
)

zbuf = io.BytesIO()
with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
    for row in rows:
        z.writestr(Path(row["file_name"]).stem + ".csv", rows_to_csv([row]))
c2.download_button(
    "Download one CSV per PDF (zip)",
    zbuf.getvalue(),
    "district_court_csvs.zip", "application/zip",
)
