# District Court Decisions: Documents to Structured Insights

A proof of concept (PoC) on Snowflake and AWS. It reads decisions of the **District Court of New Zealand** (PDF) and turns them into tables you can query. It answers one headline question:

> **How do sentencing discounts in District Court decisions compare before and after the Sentencing (Reform) Amendment Act 2025 came into force on 29 June 2025?**

The Act caps discounts for personal mitigating factors at 40% (unless that gives a manifestly unjust result). It also puts guilty plea discounts on a sliding scale with a maximum of 25%. Most published District Court decisions are sentencing notes. So they are a good test: each note contains the judge's calculation as text (starting point, uplifts, discounts, end sentence). The PoC turns that text into numbers.

A small, hand-picked sample shows that the **method** works. It is not evidence about how the law works in practice. Say this in the demo.

## Architecture

```
 You: download 20 to 50 decisions by hand from districtcourts.govt.nz
        │  app/streamlit_app.py (local intake, optional)  or  scripts/upload_judgments.py
        ▼
 S3  s3://nzdc-dev-judgments-<acct>/judgments/          (SSE-S3, private)
        │  storage integration (IAM role, read-only)
        ▼
 Snowflake  NZDC_DEV
 ├─ RAW.JUDGMENTS_STAGE (directory table)
 ├─ RAW.PROCESS_NEW_DECISIONS()   ← task, daily, created SUSPENDED
 │    1. AI_PARSE_DOCUMENT (OCR mode)  PDF → text                     → RAW.DC_DOCS
 │    1b. EXCLUSION GATE (regex, no AI): Youth Court / Family Court
 │        → flagged, text deleted, never processed
 │    2. AI_EXTRACT   19 fields: registry, judge, charges, plea, starting point,
 │                    end sentence, reparation, publication note, ...  ┐
 │       AI_CLASSIFY  offence type (criminal) / claim type (civil)     ├→ RAW.DC_CORTEX
 │       AI_COMPLETE  3-sentence plain-English summary, no names       ┘
 │    3. BEDROCK_CASE_BRIEF (sentencing notes only): the "sentencing ladder",
 │       every uplift and discount in % and months, end sentence   → RAW.DC_BEDROCK
 │          API integration → API Gateway (IAM) → Lambda → Bedrock (Claude)
 ├─ dbt  STAGING → MARTS: fct_dc_decisions (case_name MASKED), fct_sentencing_adjustments,
 │       agg_sentencing_reform, agg_registry_activity, bridges; eval vs hand labels
 ├─ OPS  masking policy, run log, cost views, budget
 └─ Streamlit in Snowflake: District Court Insights
```

**Why two AI layers?** Cortex does the cheap work on every decision: read the PDF, pull out fields, classify, summarise. Bedrock does only the part that needs reasoning, and only for sentencing notes: turning "I allow 25 per cent for your early guilty plea and a further 10 per cent for remorse" into an ordered list of numbers that should add up to the end sentence. dbt then **checks the arithmetic** (starting point + uplifts - discounts = end sentence) and compares Bedrock's end sentence with an independent rule-based read. Rows that disagree get `needs_review = true`.

## How this maps to the judging criteria

| Criterion | Where | What to show |
|---|---|---|
| CI/CD + IaC | `terraform/`, `.github/workflows/ci.yml`, `scripts/deploy.sh` | PR = fmt, validate, lint, plan. Merge = deploy dev. Manual run = prod, gated by GitHub Environment reviewers. AWS auth by OIDC. `terraform destroy` + `apply` rebuilds everything when a trial runs out. |
| RBAC + governance | `terraform/snowflake.tf`, `sql/02_pipeline.sql` | Privileges → **database roles** (`RAW_RW`, `ANALYTICS_RW`, `ANALYTICS_R`) → **account roles** (`_PIPELINE`, `_TRANSFORMER`, `_ANALYST`) → users. `CORTEX_USER` only on the pipeline role. **Masking policy** on `case_name`: only the pipeline role sees party names. **Exclusion gate** for Youth and Family Court, with two dbt tests that fail if one ever reaches a mart. |
| Warehouse optimisation | `snowflake_warehouse.wh` | ONE shared XS warehouse, 60 s auto-suspend. Workloads are separated by role and `QUERY_TAG`, not by extra warehouses. AI functions bill as serverless, so a bigger warehouse does not make them faster. |
| Monitoring | `terraform/`, `sql/03_monitoring.sql` | Resource monitor, Snowflake budget (catches serverless AI spend), AWS budget, Lambda concurrency cap, API throttling, per-run `MAX_DOCS`. Views: credits per day, AI credits per model, AI cost per run, pipeline health (incl. excluded count), task failures. |
| dbt | `dbt/` | Sources, staging, marts, a duration-parsing macro, reform-date variables, generic + governance tests, sanity tests (guilty plea ≤ 25%), seed-based accuracy eval. |
| AI (Cortex + Bedrock) | `sql/02_pipeline.sql`, `lambda/` | AI_PARSE_DOCUMENT, AI_EXTRACT (JSON schema), AI_CLASSIFY (multi-label), AI_COMPLETE; Bedrock through an external function for the sentencing arithmetic. |

## Get the documents (read this first)

**Source: districtcourts.govt.nz only.** Download each decision by hand from the District Court's published judgments. Do not use NZLII and do not use a scraper. NZLII's copyright policy prohibits robots, and AustLII (which runs NZLII) restricts AI-related uses of its case law. Nothing in this repo crawls a website.

What to pick (20 to 50 PDFs):
- **About 70% criminal sentencing notes**, half dated **before 29 June 2025** and half **after**. This is what makes the reform comparison work.
- A few offence types: family violence, drink driving, dishonesty, drugs.
- **About 30% civil** decisions (for example, Tenancy Tribunal or Disputes Tribunal appeals, debt claims).
- **Do not download Youth Court (NZYC) or Family Court (NZFC) decisions.** If one gets in by mistake, the exclusion gate catches it.

Legal and ethical notes:
- Under the Copyright Act 1994, s 27(g), no copyright exists in New Zealand court judgments. The District Court website allows copying for personal or in-house use, and asks you to contact them for other uses. This is a non-commercial training PoC. Keep the set small and do not republish it.
- Many District Court decisions start with a **NOTE** about publication restrictions (for example, s 203 of the Criminal Procedure Act 2011). The pipeline captures the note in `publication_note`. The prompts tell the models never to name defendants, victims, complainants or witnesses. The marts mask party names.
- With cross-region inference turned on, text can leave the Sydney region for inference. Say this in your design notes.

## Setup

### Prerequisites
Snowflake trial (Enterprise edition, which masking policies need; AWS ap-southeast-2 is best), AWS account with Bedrock model access, Terraform 1.6+, **Python 3.11 or 3.12** (not 3.9.7), Snowflake CLI (`snow`), `python -m pip install -r requirements.txt`.

### Steps
1. **Admin setup (once).** In Snowsight, as ACCOUNTADMIN, run `sql/00_admin_setup.sql`. Set the public keys for `TERRAFORM_SVC` and `NZDC_PIPELINE_SVC`.
2. **Bedrock.** Turn on access to your model in the AWS console. Put its model ID or inference profile ID in `bedrock_model_id`.
3. **Terraform.**
   ```bash
   cp terraform/terraform.tfvars.example terraform/terraform.tfvars   # fill in
   terraform -chdir=terraform init
   terraform -chdir=terraform apply
   ```
4. **Grant roles to the service user** (ACCOUNTADMIN):
   `GRANT ROLE NZDC_DEV_PIPELINE TO USER NZDC_PIPELINE_SVC; GRANT ROLE NZDC_DEV_TRANSFORMER TO USER NZDC_PIPELINE_SVC;`
5. **Snowflake CLI connection** named `nzdc` in `~/.snowflake/config.toml` (user `NZDC_PIPELINE_SVC`, key-pair auth).
6. **Deploy SQL + dbt:** `./scripts/deploy.sh dev`
7. **Monitoring (once, ACCOUNTADMIN):** edit the email in `sql/03_monitoring.sql`, then run it.
8. **Load decisions** with the intake app (below) or: `python scripts/upload_judgments.py --bucket "$(terraform -chdir=terraform output -raw s3_bucket)"`
9. **First run, small, no Bedrock:**
   ```sql
   USE ROLE NZDC_DEV_PIPELINE;
   CALL NZDC_DEV.RAW.PROCESS_NEW_DECISIONS(5, 'mistral-large2', FALSE);
   SELECT relative_path, excluded_reason, page_count FROM NZDC_DEV.RAW.DC_DOCS;
   ```
   Then the full run: `CALL NZDC_DEV.RAW.PROCESS_NEW_DECISIONS();`
10. **dbt:** `cd dbt && cp profiles.yml.example profiles.yml && dbt deps && dbt build --profiles-dir .`
11. **Streamlit in Snowflake:** create the app from `streamlit/streamlit_app.py` (steps at the top of the file).

### Local intake app
`app/streamlit_app.py` runs on your laptop. It needs no Snowflake or AWS account, so you can use it on day one.
- Reads the PDF text layer with `pypdf` (no OCR; scanned PDFs are flagged and skipped).
- Runs the same **exclusion gate** as the pipeline: Youth Court and Family Court decisions are flagged, their text is dropped, and they are never uploaded.
- Pulls out District Court fields with rules: citation, registry, file number, criminal or civil, judge, dates, document type, publication note, starting point, end sentence, home detention, guilty plea %, personal mitigation %, reparation, civil amounts, sections cited.
- Shows a before and after reform table for sentencing notes and flags personal mitigation over 40% after 29 June 2025.
- Lets you fix fields, download CSV or JSONL, and upload the usable PDFs to S3.

```bash
python -m pip install -r app/requirements.txt
streamlit run app/streamlit_app.py
```
The rule-based fields are a **baseline**. In the demo, compare them with the Cortex and Bedrock fields to show what the AI adds, for example word numbers ("two years and three months") and the full ordered ladder of adjustments.

## Measure accuracy (judges will ask)
Open 15 to 20 decisions yourself. Fill in `dbt/seeds/gold_labels.csv` from the PDF, **not** from the AI output: citation, registry, judgment date, document type, and for sentencing notes the sentence type, end sentence in months and guilty plea %. Then run `dbt seed && dbt run -s eval_extraction_accuracy`.

## Demo script (10 minutes)
1. The question: the 2025 reform and why sentencing notes are the right documents.
2. Local intake app: drop in 10 PDFs, including one Youth Court decision. Show it is excluded.
3. Terraform plan and the GitHub Actions run (CI/CD).
4. `CALL RAW.PROCESS_NEW_DECISIONS();` then `SELECT * FROM OPS.V_PIPELINE_HEALTH;` (includes the excluded count).
5. Streamlit in Snowflake: the reform tab, then one decision's sentencing ladder with the arithmetic check.
6. RBAC: `SELECT case_name FROM MARTS.FCT_DC_DECISIONS` as ANALYST (masked), then as PIPELINE (visible).
7. `eval_extraction_accuracy`, then the cost views and the resource monitor.

## Known limits
- The reform comparison needs enough decisions on each side of 29 June 2025. With 20 to 50 documents, report counts, not trends.
- Judges do not always state a percentage for each factor. Some give months, some give one combined discount. Bedrock returns null where the judge gives no number, and the arithmetic check shows where steps are missing.
- The District Court publishes only a selection of its decisions. The sample is not representative of all District Court work.
- Cortex function, model and usage-view names change often. Check the Snowflake docs if a call fails.
- API Gateway has a 29 s default timeout. District Court decisions are short, so this is rarely a problem.
- Terraform `snowflake_stage` and the integration resources are "preview" in provider v2. Run `terraform validate` first and pin the version you test with.
