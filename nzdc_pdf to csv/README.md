# NZ District Court PDF to CSV

Input: one or more District Court PDFs.
Output: CSV with the same 8 columns for every PDF, whatever the type of document.

| Column | Filled for |
|---|---|
| `file_name` | all PDFs |
| `citation` | all PDFs |
| `registry` | all PDFs (empty for courts with no registry, for example the Court of Appeal) |
| `judgment_date` (`YYYY-MM-DD`) | all PDFs |
| `document_type` | all PDFs |
| `sentence_type` | sentencing notes only |
| `end_sentence_months` | sentencing notes only |
| `guilty_plea_pct` | sentencing notes only |

An empty cell means the field does not apply or the app did not find it.
`guilty_plea_pct` = `0` means no guilty plea (the defendant was found guilty after a trial or hearing).

## Run the app

```bash
cd ~/Desktop/"aws datathon"/nzdc_csv
pip install -r requirements.txt
streamlit run app.py
```

The app has two download buttons:
- **One CSV (all PDFs):** one header row, then one row for each PDF.
- **One CSV per PDF (zip):** one file for each PDF. Each file has the same header and one row.

## Run without the app

```bash
python batch.py "/path/to/pdfs" results.csv             # one CSV for all PDFs
python batch.py "/path/to/pdfs" csv_folder --per-pdf    # one CSV for each PDF
```

## Tests

```bash
python -m pytest -q
```

The tests check the values for the PDFs in `samples/`. They also check that every CSV has the same columns.

## Files

- `schema.py`: the fixed column list and the CSV writer. Change the columns here only.
- `extractor.py`: the extraction rules (a copy from `nzdc_extractor`).
- `app.py`, `batch.py`: the two ways to run it.
