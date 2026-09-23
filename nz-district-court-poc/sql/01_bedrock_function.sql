-- =====================================================================
-- 01_bedrock_function.sql
-- External function: Snowflake -> API Gateway -> Lambda -> Bedrock.
-- Run as PIPELINE role before 02_pipeline.sql.
--
-- Replace <BEDROCK_API_URL> with:  terraform output -raw bedrock_api_url
-- deploy.sh does this for you.
-- =====================================================================
USE ROLE NZDC_DEV_PIPELINE;
USE DATABASE NZDC_DEV;
USE SCHEMA RAW;

CREATE OR REPLACE EXTERNAL FUNCTION RAW.BEDROCK_CASE_BRIEF(decision_text STRING, case_type STRING)
    RETURNS VARIANT
    API_INTEGRATION = NZDC_DEV_BEDROCK_API_INT
    MAX_BATCH_ROWS = 1          -- one judgment per Lambda call; keeps each call under the API timeout
    COMPRESSION = AUTO
    COMMENT = 'Sentencing arithmetic (starting point, adjustments, end sentence) from a Bedrock model'
    AS '<BEDROCK_API_URL>';

-- Smoke test (costs one Bedrock call):
-- SELECT RAW.BEDROCK_CASE_BRIEF(
--   'IN THE DISTRICT COURT AT AUCKLAND ... I adopt a starting point of two years imprisonment. '
--   || 'I allow 25 per cent for your guilty plea and 10 per cent for remorse ... end sentence of 15 months.',
--   'criminal');
