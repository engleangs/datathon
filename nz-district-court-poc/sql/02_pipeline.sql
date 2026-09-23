-- =====================================================================
-- 02_pipeline.sql
-- District Court decisions: PDF -> text -> structured fields, inside Snowflake.
-- Run as the PIPELINE role after terraform apply and 01_bedrock_function.sql.
-- CI replaces NZDC_DEV with NZDC_PROD for the prod environment.
-- =====================================================================
USE ROLE NZDC_DEV_PIPELINE;
USE WAREHOUSE NZDC_DEV_WH;
USE DATABASE NZDC_DEV;
USE SCHEMA RAW;
ALTER SESSION SET QUERY_TAG = 'nzdc:pipeline:setup';

-- ---------------------------------------------------------------------
-- Governance: mask party names for everyone except the pipeline role.
-- dbt attaches this policy to MARTS.FCT_DC_DECISIONS.CASE_NAME.
-- "R v Smith" -> "R v [withheld]". Needs Enterprise edition (trials are Enterprise).
-- ---------------------------------------------------------------------
CREATE MASKING POLICY IF NOT EXISTS OPS.MASK_PARTY_NAME AS (val STRING) RETURNS STRING ->
    CASE
        WHEN IS_ROLE_IN_SESSION('NZDC_DEV_PIPELINE') THEN val
        ELSE REGEXP_REPLACE(val, '\\s+v\\s+.+$', ' v [withheld]')
    END;
GRANT APPLY ON MASKING POLICY OPS.MASK_PARTY_NAME TO ROLE NZDC_DEV_TRANSFORMER;

-- ---------------------------------------------------------------------
-- Tables (one row per decision PDF, keyed by relative_path)
-- ---------------------------------------------------------------------

-- Layer 1: parsed text + exclusion gate
CREATE TABLE IF NOT EXISTS RAW.DC_DOCS (
    relative_path   STRING        NOT NULL PRIMARY KEY,
    file_size_bytes NUMBER,
    page_count      NUMBER,
    citation_found  STRING,         -- regex, before any AI
    excluded_reason STRING,         -- not null = no AI processing, text removed
    full_text       STRING,
    parse_error     STRING,
    parsed_at       TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Layer 2: Cortex fields for EVERY included decision
CREATE TABLE IF NOT EXISTS RAW.DC_CORTEX (
    relative_path    STRING NOT NULL PRIMARY KEY,
    extract_raw      VARIANT,       -- AI_EXTRACT
    offence_type_raw VARIANT,       -- AI_CLASSIFY (criminal)
    civil_type_raw   VARIANT,       -- AI_CLASSIFY (civil)
    summary          STRING,        -- AI_COMPLETE
    summary_model    STRING,
    processed_at     TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Layer 3: Bedrock sentencing arithmetic (sentencing notes only)
CREATE TABLE IF NOT EXISTS RAW.DC_BEDROCK (
    relative_path   STRING NOT NULL PRIMARY KEY,
    brief_raw       VARIANT,
    reason          STRING,
    processed_at    TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS OPS.PIPELINE_RUNS (
    run_id          STRING DEFAULT UUID_STRING(),
    started_at      TIMESTAMP_LTZ,
    finished_at     TIMESTAMP_LTZ,
    docs_parsed     NUMBER,
    docs_excluded   NUMBER,
    docs_extracted  NUMBER,
    docs_bedrock    NUMBER,
    status          STRING,
    error_message   STRING
);

-- ---------------------------------------------------------------------
-- Stored procedure: process only NEW files (idempotent, safe to re-run)
-- ---------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE RAW.PROCESS_NEW_DECISIONS(
    MAX_DOCS       NUMBER  DEFAULT 25,              -- cost guard per run
    SUMMARY_MODEL  STRING  DEFAULT 'mistral-large2',
    USE_BEDROCK    BOOLEAN DEFAULT TRUE
)
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS CALLER
AS
$$
DECLARE
    started    TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP();
    n_parsed   NUMBER DEFAULT 0;
    n_excluded NUMBER DEFAULT 0;
    n_extract  NUMBER DEFAULT 0;
    n_bedrock  NUMBER DEFAULT 0;
BEGIN
    ALTER SESSION SET QUERY_TAG = 'nzdc:pipeline:run';
    ALTER STAGE RAW.JUDGMENTS_STAGE REFRESH;

    -- 1. PARSE. OCR mode: District Court PDFs are born-digital, text-heavy, few tables.
    INSERT INTO RAW.DC_DOCS (relative_path, file_size_bytes, page_count, citation_found, full_text, parse_error)
    WITH new_files AS (
        SELECT d.relative_path, d.size
        FROM DIRECTORY(@RAW.JUDGMENTS_STAGE) d
        LEFT JOIN RAW.DC_DOCS j ON j.relative_path = d.relative_path
        WHERE j.relative_path IS NULL
          AND LOWER(d.relative_path) LIKE '%.pdf'
        ORDER BY d.last_modified
        LIMIT :MAX_DOCS
    ),
    parsed AS (
        SELECT relative_path, size,
               PARSE_JSON(TO_VARCHAR(
                   AI_PARSE_DOCUMENT(TO_FILE('@RAW.JUDGMENTS_STAGE', relative_path),
                                     {'mode': 'OCR', 'page_split': TRUE})
               )) AS p
        FROM new_files
    ),
    texts AS (
        SELECT parsed.relative_path,
               ANY_VALUE(parsed.size)                                          AS size,
               COALESCE(ANY_VALUE(parsed.p):metadata:pageCount::NUMBER,
                        ARRAY_SIZE(ANY_VALUE(parsed.p):pages))                 AS page_count,
               LISTAGG(pg.value:content::STRING, '\n\n')
                   WITHIN GROUP (ORDER BY pg.value:index::NUMBER)              AS full_text,
               ANY_VALUE(parsed.p):errorInformation::STRING                    AS parse_error
        FROM parsed, LATERAL FLATTEN(input => parsed.p:pages, OUTER => TRUE) pg
        GROUP BY parsed.relative_path
    )
    SELECT relative_path, size, page_count,
           REGEXP_SUBSTR(LEFT(full_text, 5000), '\\[[0-9]{4}\\]\\s*NZ[A-Za-z]+\\s*[0-9]+'),
           full_text, parse_error
    FROM texts;
    n_parsed := SQLROWCOUNT;

    -- 1b. EXCLUSION GATE (before any AI). Youth Court and Family Court decisions
    --     carry strict publication rules. They get NO AI processing and their text is deleted.
    UPDATE RAW.DC_DOCS
       SET excluded_reason = CASE
               WHEN citation_found ILIKE '%NZYC%' OR LEFT(full_text, 3000) ILIKE '%YOUTH COURT%'  THEN 'youth_court'
               WHEN citation_found ILIKE '%NZFC%' OR LEFT(full_text, 3000) ILIKE '%FAMILY COURT%' THEN 'family_court'
               WHEN citation_found IS NOT NULL AND citation_found NOT ILIKE '%NZDC%'              THEN 'not_district_court'
           END,
           full_text = NULL
     WHERE excluded_reason IS NULL
       AND full_text IS NOT NULL
       AND (   citation_found ILIKE '%NZYC%' OR citation_found ILIKE '%NZFC%'
            OR LEFT(full_text, 3000) ILIKE '%YOUTH COURT%' OR LEFT(full_text, 3000) ILIKE '%FAMILY COURT%'
            OR (citation_found IS NOT NULL AND citation_found NOT ILIKE '%NZDC%'));
    n_excluded := SQLROWCOUNT;

    -- 2. CORTEX: fields, classification and summary for every included decision.
    --    DC decisions are short (most under 20 pages), so we send up to 60k characters.
    INSERT INTO RAW.DC_CORTEX (relative_path, extract_raw, offence_type_raw, civil_type_raw, summary, summary_model)
    WITH todo AS (
        SELECT d.relative_path,
               CASE WHEN LENGTH(d.full_text) <= 60000 THEN d.full_text
                    ELSE LEFT(d.full_text, 40000) || '\n\n[...]\n\n' || RIGHT(d.full_text, 20000)
               END AS doc_text,
               IFF(REGEXP_LIKE(LEFT(d.full_text, 5000), '.*CIV-[0-9]{4}.*', 's'), 'civil', 'criminal') AS case_type_hint
        FROM RAW.DC_DOCS d
        LEFT JOIN RAW.DC_CORTEX c ON c.relative_path = d.relative_path
        WHERE c.relative_path IS NULL
          AND d.excluded_reason IS NULL
          AND d.full_text IS NOT NULL
          AND d.parse_error IS NULL
    )
    SELECT
        relative_path,
        AI_EXTRACT(
            text => doc_text,
            responseFormat => {
              'schema': {
                'type': 'object',
                'properties': {
                  'case_name':         {'type': 'string', 'description': 'Case name as in the title, for example R v Smith or Police v Jones or ABC Ltd v XYZ Ltd'},
                  'neutral_citation':  {'type': 'string', 'description': 'Neutral citation such as [2024] NZDC 12345'},
                  'registry':          {'type': 'string', 'description': 'Place where the court sat, from the line IN THE DISTRICT COURT AT <place>'},
                  'file_number':       {'type': 'string', 'description': 'Court file number, for example CRI-2023-004-001234 or CIV-2022-092-000456'},
                  'judge':             {'type': 'string', 'description': 'Name of the District Court Judge, for example Judge A B Smith'},
                  'judgment_date':     {'type': 'string', 'description': 'Date of the judgment or sentencing, YYYY-MM-DD'},
                  'hearing_date':      {'type': 'string', 'description': 'Date of the hearing, YYYY-MM-DD'},
                  'document_type':     {'type': 'string', 'description': 'One of: sentencing, reserved judgment, oral judgment, appeal, other'},
                  'prosecuting_agency':{'type': 'string', 'description': 'Criminal only: who prosecuted, for example New Zealand Police, the Crown, WorkSafe, a council'},
                  'charges':           {'type': 'array',  'description': 'Offences the defendant was sentenced for or charged with, short description each, no names'},
                  'charge_sections':   {'type': 'array',  'description': 'Section references for the charges, for example s 188(2) Crimes Act 1961'},
                  'plea':              {'type': 'string', 'description': 'guilty, not guilty, or unknown'},
                  'starting_point':    {'type': 'string', 'description': 'Starting point adopted by the judge, as written, for example 2 years 6 months imprisonment'},
                  'end_sentence':      {'type': 'string', 'description': 'Final sentence imposed, as written, for example 9 months home detention'},
                  'reparation':        {'type': 'string', 'description': 'Reparation ordered, with dollar amount'},
                  'civil_outcome':     {'type': 'string', 'description': 'Civil only: result and amount awarded'},
                  'publication_note':  {'type': 'string', 'description': 'Text of any NOTE or EDITORIAL NOTE about publication, suppression or deleted details at the top of the decision'},
                  'statutes_cited':    {'type': 'array',  'description': 'Acts cited, for example Sentencing Act 2002, Land Transport Act 1998'},
                  'cases_cited':       {'type': 'array',  'description': 'Citations of other cases, for example [2019] NZCA 123'}
                }
              }
            }
        ),
        IFF(case_type_hint = 'criminal',
            AI_CLASSIFY(LEFT(doc_text, 15000),
                ['violence', 'family violence', 'sexual offending', 'drugs', 'dishonesty and theft',
                 'driving (excess alcohol or drugs)', 'driving (dangerous or careless)',
                 'weapons and firearms', 'breach of court orders', 'health and safety',
                 'regulatory', 'other'],
                {'output_mode': 'multi',
                 'task_description': 'Classify the types of offending in this New Zealand District Court sentencing decision'}),
            NULL),
        IFF(case_type_hint = 'civil',
            AI_CLASSIFY(LEFT(doc_text, 15000),
                ['contract and debt', 'tenancy appeal', 'disputes tribunal appeal', 'property',
                 'employment', 'negligence', 'costs', 'other'],
                {'task_description': 'Classify the type of this New Zealand District Court civil decision'}),
            NULL),
        AI_COMPLETE(
            :SUMMARY_MODEL,
            'Summarise this New Zealand District Court decision for a non-lawyer in 3 short sentences: '
            || 'what the case was about, what the court decided, and why. Plain English. '
            || 'Do not name the defendant, any victim, complainant or witness.\n\n' || LEFT(doc_text, 30000)
        ),
        :SUMMARY_MODEL
    FROM todo;
    n_extract := SQLROWCOUNT;

    -- 3. BEDROCK: sentencing arithmetic for sentencing notes only.
    --    Cortex tells us what KIND of document it is; Bedrock does the reasoning.
    IF (USE_BEDROCK) THEN
        INSERT INTO RAW.DC_BEDROCK (relative_path, brief_raw, reason)
        WITH todo AS (
            SELECT d.relative_path, d.full_text
            FROM RAW.DC_DOCS d
            JOIN RAW.DC_CORTEX c ON c.relative_path = d.relative_path
            LEFT JOIN RAW.DC_BEDROCK b ON b.relative_path = d.relative_path
            WHERE b.relative_path IS NULL
              AND d.excluded_reason IS NULL
              AND (LOWER(c.extract_raw:response:document_type::STRING) LIKE '%sentenc%'
                   OR NULLIF(TRIM(c.extract_raw:response:end_sentence::STRING), '') IS NOT NULL)
        )
        SELECT relative_path, RAW.BEDROCK_CASE_BRIEF(full_text, 'criminal'), 'sentencing_note'
        FROM todo;
        n_bedrock := SQLROWCOUNT;
    END IF;

    INSERT INTO OPS.PIPELINE_RUNS (started_at, finished_at, docs_parsed, docs_excluded, docs_extracted, docs_bedrock, status)
    VALUES (:started, CURRENT_TIMESTAMP(), :n_parsed, :n_excluded, :n_extract, :n_bedrock, 'SUCCESS');

    RETURN OBJECT_CONSTRUCT('parsed', n_parsed, 'excluded', n_excluded,
                            'extracted', n_extract, 'bedrock', n_bedrock);
EXCEPTION
    WHEN OTHER THEN
        INSERT INTO OPS.PIPELINE_RUNS (started_at, finished_at, docs_parsed, docs_excluded, docs_extracted, docs_bedrock, status, error_message)
        VALUES (:started, CURRENT_TIMESTAMP(), :n_parsed, :n_excluded, :n_extract, :n_bedrock, 'FAILED', :SQLERRM);
        RAISE;
END;
$$;

-- ---------------------------------------------------------------------
-- Scheduled task. Created SUSPENDED so it never burns credits by surprise.
-- Run on demand:  EXECUTE TASK RAW.DC_PIPELINE_TASK;
-- First test:     CALL RAW.PROCESS_NEW_DECISIONS(5, 'mistral-large2', FALSE);
-- ---------------------------------------------------------------------
CREATE OR REPLACE TASK RAW.DC_PIPELINE_TASK
    WAREHOUSE = NZDC_DEV_WH
    SCHEDULE = 'USING CRON 0 6 * * * Pacific/Auckland'
    USER_TASK_TIMEOUT_MS = 3600000
    SUSPEND_TASK_AFTER_NUM_FAILURES = 2
    COMMENT = 'Daily: parse, gate, extract and analyse any new District Court decisions'
AS
    CALL RAW.PROCESS_NEW_DECISIONS(25, 'mistral-large2', TRUE);

-- ALTER TASK RAW.DC_PIPELINE_TASK RESUME;   -- only when you want the schedule on
