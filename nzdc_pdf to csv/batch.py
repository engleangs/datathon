"""Convert a folder of PDFs to CSV without the web app.

Usage:
  python batch.py <pdf_folder> [output.csv]          one CSV for all PDFs
  python batch.py <pdf_folder> <output_folder> --per-pdf   one CSV for each PDF
"""
import sys
from pathlib import Path

from schema import pdf_to_row, rows_to_csv

args = [a for a in sys.argv[1:] if not a.startswith("--")]
per_pdf = "--per-pdf" in sys.argv
folder = Path(args[0])
out = Path(args[1]) if len(args) > 1 else Path("csv_output" if per_pdf else "district_court.csv")

pdfs = sorted(folder.glob("*.pdf"))
rows = []
for i, p in enumerate(pdfs, 1):
    rows.append(pdf_to_row(p.read_bytes(), p.name))
    print(f"[{i}/{len(pdfs)}] {p.name}")

if per_pdf:
    out.mkdir(parents=True, exist_ok=True)
    for row in rows:
        (out / (Path(row["file_name"]).stem + ".csv")).write_text(rows_to_csv([row]), encoding="utf-8")
    print(f"Wrote {len(rows)} CSV files to {out}")
else:
    out.write_text(rows_to_csv(rows), encoding="utf-8")
    print(f"Wrote {out}")
