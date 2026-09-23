# Architecture

## Agent boundary

The MVP agent runs **inside the Python application on the OVH host**.

Amazon Bedrock provides the model inference. The Strands SDK provides the local agent loop and tool orchestration.

The agent may call only:

1. `search_judgment`
2. `get_page`
3. `validate_reference`
4. `scan_publication_restriction_markers`

It does not receive shell access, arbitrary HTTP access, or arbitrary SQL execution.

## Persistence boundary

The agent returns a Pydantic-validated `CourtCaseExtraction`.

The application then performs deterministic checks against the original PDF.

Only after a user reviews the result can the application call the Snowflake writer.

## Snowflake/dbt boundary

```text
RAW.DOCUMENTS
RAW.CASE_EXTRACTIONS
       |
       v
stg_case_extractions
       |
       v
int_case_quality
       |
       +-----------------------+
       |                       |
       v                       v
fct_cases              fct_verified_cases
       |
       +-----------------------+
       |                       |
       v                       v
dim_legislation        fct_case_citations
```

dbt models are views in the MVP. That makes newly inserted RAW rows immediately visible through the analytical layer after the models have initially been deployed.
