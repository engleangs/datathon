-- =====================================================================
-- 03_monitoring.sql
-- Cost guardrails and usage views.
-- Guardrails in this PoC (4 layers):
--   1. Resource monitor on the warehouse (Terraform): notify 50/80 %, suspend 100 %.
--   2. Snowflake budget (below): covers serverless + AI spend the monitor cannot see.
--   3. AWS budget (Terraform) + Lambda concurrency cap + API Gateway throttling.
--   4. Per-run cap: PROCESS_NEW_DECISIONS(MAX_DOCS => 25) and text truncation.
-- ACCOUNT_USAGE views lag by up to a few hours. View names for AI usage change
-- often, so check "Cortex AI cost" in the Snowflake docs if a view is missing.
-- =====================================================================

-- ---------------------------------------------------------------------
-- A. Snowflake custom budget (run once as ACCOUNTADMIN)
-- ---------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;
USE DATABASE NZDC_DEV;
USE SCHEMA OPS;

-- Email notifications need a verified email on your user and this integration.
CREATE NOTIFICATION INTEGRATION IF NOT EXISTS NZDC_BUDGET_EMAIL
    TYPE = EMAIL
    ENABLED = TRUE
    ALLOWED_RECIPIENTS = ('you@example.com');

CREATE SNOWFLAKE.CORE.BUDGET IF NOT EXISTS OPS.NZDC_BUDGET();
CALL OPS.NZDC_BUDGET!SET_SPENDING_LIMIT(15);          -- credits per month
CALL OPS.NZDC_BUDGET!SET_EMAIL_NOTIFICATIONS('NZDC_BUDGET_EMAIL', 'you@example.com');
CALL OPS.NZDC_BUDGET!ADD_RESOURCE(
     SYSTEM$REFERENCE('WAREHOUSE', 'NZDC_DEV_WH', 'SESSION', 'APPLYBUDGET'));
CALL OPS.NZDC_BUDGET!ADD_RESOURCE(
     SYSTEM$REFERENCE('DATABASE', 'NZDC_DEV', 'SESSION', 'APPLYBUDGET'));

-- Let the pipeline role read usage data for the views below.
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE NZDC_DEV_PIPELINE;

-- ---------------------------------------------------------------------
-- B. Monitoring views (run as PIPELINE role)
-- ---------------------------------------------------------------------
USE ROLE NZDC_DEV_PIPELINE;

-- Warehouse credits per day
CREATE OR REPLACE VIEW OPS.V_WAREHOUSE_CREDITS_DAILY AS
SELECT DATE_TRUNC('day', start_time) AS usage_day,
       warehouse_name,
       SUM(credits_used)            AS credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name = 'NZDC_DEV_WH'
GROUP BY 1, 2;

-- AI function credits per day, function and model
CREATE OR REPLACE VIEW OPS.V_CORTEX_CREDITS_DAILY AS
SELECT DATE_TRUNC('day', start_time) AS usage_day,
       function_name,
       model_name,
       SUM(tokens)                   AS tokens,
       SUM(token_credits)            AS credits
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FUNCTIONS_USAGE_HISTORY
GROUP BY 1, 2, 3;

-- Document parsing credits (AI_PARSE_DOCUMENT is billed per page)
CREATE OR REPLACE VIEW OPS.V_DOC_PARSE_CREDITS_DAILY AS
SELECT DATE_TRUNC('day', start_time) AS usage_day,
       function_name,
       SUM(page_count)               AS pages,
       SUM(credits_used)             AS credits
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_DOCUMENT_PROCESSING_USAGE_HISTORY
GROUP BY 1, 2;

-- AI cost per pipeline run: join AI usage to the pipeline's query tag
CREATE OR REPLACE VIEW OPS.V_AI_CREDITS_PER_RUN AS
SELECT q.query_tag,
       DATE_TRUNC('hour', q.start_time) AS run_hour,
       SUM(c.token_credits)             AS ai_credits,
       COUNT(DISTINCT q.query_id)       AS queries
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FUNCTIONS_QUERY_USAGE_HISTORY c
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q ON q.query_id = c.query_id
WHERE q.query_tag LIKE 'nzdc:%'
GROUP BY 1, 2;

-- Pipeline health: last 30 runs
CREATE OR REPLACE VIEW OPS.V_PIPELINE_HEALTH AS
SELECT run_id, started_at, finished_at,
       DATEDIFF('second', started_at, finished_at) AS duration_s,
       docs_parsed, docs_excluded, docs_extracted, docs_bedrock, status, error_message
FROM OPS.PIPELINE_RUNS
QUALIFY ROW_NUMBER() OVER (ORDER BY started_at DESC) <= 30;

-- The Streamlit app (owned by the TRANSFORMER role) shows run health.
GRANT SELECT ON VIEW OPS.V_PIPELINE_HEALTH TO ROLE NZDC_DEV_TRANSFORMER;

-- Task failures
CREATE OR REPLACE VIEW OPS.V_TASK_FAILURES AS
SELECT name, state, error_message, scheduled_time, completed_time
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
       SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())))
WHERE state = 'FAILED';

-- ---------------------------------------------------------------------
-- C. Quick checks
-- ---------------------------------------------------------------------
-- SHOW RESOURCE MONITORS LIKE 'NZDC_DEV_RM';
-- CALL OPS.NZDC_BUDGET!GET_SPENDING_HISTORY();
-- SELECT * FROM OPS.V_PIPELINE_HEALTH;
