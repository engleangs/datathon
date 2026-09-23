# NZ Court Intelligence — Bootstrap

Datathon MVP for extracting **traceable structured information from public New Zealand court judgment PDFs**.

## Stack

- **UI:** Streamlit
- **Agent runtime:** Python + Strands Agents SDK
- **Foundation model:** Amazon Bedrock
- **Agent tools:** page reader, document search, reference validator, publication-restriction marker scan
- **Warehouse:** Snowflake
- **Transformation / quality:** dbt + Snowflake
- **Runtime:** Docker Compose on OVH Linux
- **CI/CD:** GitHub Actions → `/datathon/prod`

## Architecture

```text
Public NZ judgment PDF
        |
        v
+-----------------------+
| Streamlit on OVH      |
+-----------+-----------+
            |
            v
+-----------------------+
| Strands Court Agent   |
| Amazon Bedrock model  |
+-----------+-----------+
            |
     +------+------+------------------+
     |             |                  |
     v             v                  v
 search       get page        validate reference
 judgment                          |
     |                             v
     +--------------------> publication-marker scan
                                   |
                                   v
                         Structured Pydantic result
                                   |
                                   v
                         Deterministic validation
                                   |
                              human review?
                              /          \
                            yes          no
                             |            |
                             +------v-----+
                                    |
                                    v
                           Snowflake RAW
                                    |
                                    v
                                   dbt
                                    |
                      +-------------+-------------+
                      |                           |
                      v                           v
                verified cases             legislation /
                    view                    citation views
```

The **agent does not receive an unrestricted SQL or shell tool**. Persistence is handled deterministically by the application after validation/review.

## Repository

```text
.
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   └── services/
│       ├── agent_service.py
│       ├── court_tools.py
│       ├── document_context.py
│       ├── pdf_service.py
│       ├── snowflake_service.py
│       └── validation_service.py
├── dbt_nz_court/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── sources.yml
│       ├── staging/
│       ├── intermediate/
│       └── marts/
├── deploy/nginx/
├── docs/
├── scripts/
├── sql/bootstrap.sql
├── tests/
├── .github/workflows/pipeline.yml
├── Dockerfile
├── Dockerfile.dbt
├── docker-compose.yml
├── requirements-app.txt
├── requirements-dbt.txt
├── requirements-dev.txt
└── .env.example
```

## 1. Configure AWS Bedrock

Create an IAM identity for this application with permission to invoke only the Bedrock model/inference profile you need.

Copy the environment template:

```bash
cp .env.example .env
```

At minimum configure:

```env
AWS_REGION=ap-southeast-2
BEDROCK_MODEL_ID=<your Bedrock model or inference profile>
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

For a longer-lived production deployment, prefer temporary credentials / workload identity over permanent access keys.

## 2. Configure Snowflake

Run:

```text
sql/bootstrap.sql
```

in Snowflake.

Then configure:

```env
SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_USER=...
SNOWFLAKE_PASSWORD=...
SNOWFLAKE_WAREHOUSE=...
SNOWFLAKE_DATABASE=NZ_COURT_INTELLIGENCE
SNOWFLAKE_ROLE=...
DBT_TARGET_SCHEMA=ANALYTICS
```

## 3. Run locally without Docker

Python 3.10+ is required.

```bash
python -m venv .venv
source .venv/bin/activate

pip install -r requirements-app.txt
pip install -r requirements-dev.txt

streamlit run app/main.py
```

## 4. Run with Docker

```bash
docker compose build
docker compose up -d app
docker compose logs -f app
```

Default URL:

```text
http://localhost:8501
```

Run dbt:

```bash
docker compose run --rm dbt
```

The dbt marts are **views** for the MVP, so newly inserted RAW records are visible without rebuilding a table after every PDF.

## 5. Test connectivity

Bedrock:

```bash
python scripts/check_bedrock.py
```

Snowflake:

```bash
python scripts/check_snowflake.py
```

Unit tests:

```bash
pytest -q
```

## 6. Replit

The included `.replit` starts:

```bash
streamlit run app/main.py --server.address=0.0.0.0 --server.port=8501
```

Use Replit Secrets for AWS/Snowflake credentials. Do not commit them.

## 7. OVH deployment

Target:

```text
139.99.68.73
/datathon/prod
```

See `docs/DEPLOYMENT.md`.

## Data-safety rules

This bootstrap is designed for **publicly available judgments**.

- Do not try to reverse anonymisation.
- Do not infer suppressed identities.
- Treat detected publication/suppression markers as `REVIEW_REQUIRED`.
- Preserve supporting page references and source evidence.
- Do not present this system as legal advice.
- Do not commit court PDFs or credentials to Git.
