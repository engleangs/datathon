-- =============================================================================
-- 02  ROLES AND PERMISSIONS for the existing database DATATHON_TEST.
-- Run as: ACCOUNTADMIN (the script switches to SECURITYADMIN / SYSADMIN itself).
-- Safe to rerun: everything uses IF NOT EXISTS or is a repeatable GRANT.
-- It never creates, alters or drops your tables or data.
--
-- Design:
--   * The ingestion agent (role INGESTIONAGENT) writes views and dynamic
--     tables into COURTLENS. Its own grants are NOT changed here.
--   * Engineering roles get access at DATABASE level, so every schema and
--     every object the agent creates later is covered automatically:
--       DTH_DB_READ   see and SELECT everything (tables, views, dynamic tables)
--       DTH_DB_WRITE  READ + insert/update/delete rows
--       DTH_DB_BUILD  WRITE + create schemas, tables, views, dynamic tables
--   * Data Analyst, PM, the app and judges get DTH_MART_READ ONLY: the new
--     MART schema, where script 03 builds masked secure views. They cannot
--     read the unmasked agent data in COURTLENS.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Create the roles
-- ---------------------------------------------------------------------------

-- SECURITYADMIN: built-in role for creating roles and granting access.
-- ACCOUNTADMIN includes above role
USE ROLE SECURITYADMIN;

-- Access roles: bundles of privileges on the database. People never get
-- these directly; team roles (below) get them.
CREATE ROLE IF NOT EXISTS DTH_DB_READ   COMMENT = 'SELECT on everything in DATATHON_TEST';
CREATE ROLE IF NOT EXISTS DTH_DB_WRITE  COMMENT = 'READ + change rows in DATATHON_TEST';
CREATE ROLE IF NOT EXISTS DTH_DB_BUILD  COMMENT = 'WRITE + create objects in DATATHON_TEST';
-- Read access to the masked MART views only (Data Analyst, PM, app).
CREATE ROLE IF NOT EXISTS DTH_MART_READ COMMENT = 'SELECT on masked views in DATATHON_TEST.MART only';

-- Nest them: WRITE inherits everything READ can do; BUILD inherits WRITE.
GRANT ROLE DTH_DB_READ  TO ROLE DTH_DB_WRITE;
GRANT ROLE DTH_DB_WRITE TO ROLE DTH_DB_BUILD;

-- Team (functional) roles: one per person's job. People get exactly one.
CREATE ROLE IF NOT EXISTS DTH_CLOUD_ENGINEER      COMMENT = 'CE: platform admin';
CREATE ROLE IF NOT EXISTS DTH_DATA_ENGINEER       COMMENT = 'DE: ingestion and parsing';
CREATE ROLE IF NOT EXISTS DTH_ANALYTICS_ENGINEER  COMMENT = 'AE: model, evidence, marts';
CREATE ROLE IF NOT EXISTS DTH_DATA_SCIENTIST      COMMENT = 'DS: LLM extraction and evaluation';
CREATE ROLE IF NOT EXISTS DTH_DATA_ANALYST        COMMENT = 'DA: dashboards and Streamlit app';
CREATE ROLE IF NOT EXISTS DTH_PROJECT_MANAGER     COMMENT = 'PM: read-only + Role of Cloud Engineer';

-- Capability role: holds no table access itself. The masking and row access
-- policies in 03 check for it to decide who sees real names of individuals.
CREATE ROLE IF NOT EXISTS DTH_PII_READER          COMMENT = 'Sees unmasked individual names and suppressed cases';

-- Service roles, for programs rather than people.
CREATE ROLE IF NOT EXISTS DTH_PIPELINE_SVC        COMMENT = 'AWS Lambda / Bedrock extraction job';
CREATE ROLE IF NOT EXISTS DTH_APP_VIEWER          COMMENT = 'Judges and guests: Streamlit app only';

-- Roll every new role up to SYSADMIN (Snowflake best practice), so account
-- admins can always manage objects these roles create.
-- NOTE: because DTH_PII_READER rolls up to SYSADMIN, anyone using SYSADMIN
-- sees unmasked names. Keep SYSADMIN for the Cloud Engineer only (section 6).
GRANT ROLE DTH_DB_BUILD            TO ROLE SYSADMIN;
GRANT ROLE DTH_MART_READ           TO ROLE SYSADMIN;
GRANT ROLE DTH_CLOUD_ENGINEER      TO ROLE SYSADMIN;
GRANT ROLE DTH_DATA_ENGINEER       TO ROLE SYSADMIN;
GRANT ROLE DTH_ANALYTICS_ENGINEER  TO ROLE SYSADMIN;
GRANT ROLE DTH_DATA_SCIENTIST      TO ROLE SYSADMIN;
GRANT ROLE DTH_DATA_ANALYST        TO ROLE SYSADMIN;
GRANT ROLE DTH_PROJECT_MANAGER     TO ROLE SYSADMIN;
GRANT ROLE DTH_PII_READER          TO ROLE SYSADMIN;
GRANT ROLE DTH_PIPELINE_SVC        TO ROLE SYSADMIN;
GRANT ROLE DTH_APP_VIEWER          TO ROLE SYSADMIN;

-- The agent's role: roll it up to SYSADMIN too (skip if SHOW GRANTS OF ROLE
-- INGESTIONAGENT in 01 already shows SYSADMIN). Objects are controlled by
-- their owner; without this, even ACCOUNTADMIN can't alter the agent's
-- objects. This adds no new rights to the agent itself.
GRANT ROLE INGESTIONAGENT          TO ROLE SYSADMIN;

-- 2. Warehouse and spending cap

-- SYSADMIN creates warehouses.
USE ROLE SYSADMIN;
-- One small warehouse for the team: 1 credit/hour while running, suspends
-- after 60 idle seconds, starts automatically, doesn't start at creation.
CREATE WAREHOUSE IF NOT EXISTS DTH_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Datathon team warehouse';

-- Resource monitors are ACCOUNTADMIN-only.
USE ROLE ACCOUNTADMIN;
-- Cap spend at 40 credits: email at 50% and 80%, suspend at 100%.
-- FREQUENCY = NEVER means the budget never resets. Adjust to your credits.
-- (OR REPLACE: rerunning recreates it; the next line re-attaches it.)
CREATE OR REPLACE RESOURCE MONITOR DTH_RM
  WITH CREDIT_QUOTA = 40 FREQUENCY = NEVER START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 50 PERCENT DO NOTIFY ON 80 PERCENT DO NOTIFY ON 100 PERCENT DO SUSPEND;
-- Attach the cap to the team warehouse.
ALTER WAREHOUSE DTH_WH SET RESOURCE_MONITOR = DTH_RM;

-- Every team and service role may run queries on the team warehouse.
USE ROLE SECURITYADMIN;
GRANT USAGE ON WAREHOUSE DTH_WH TO ROLE DTH_DB_READ;        -- inherited by WRITE and BUILD
GRANT USAGE ON WAREHOUSE DTH_WH TO ROLE DTH_MART_READ;      -- DA, PM
GRANT USAGE ON WAREHOUSE DTH_WH TO ROLE DTH_APP_VIEWER;     -- judges and guests
-- The Cloud Engineer can resize, suspend and monitor it.
GRANT MODIFY, MONITOR, OPERATE ON WAREHOUSE DTH_WH TO ROLE DTH_CLOUD_ENGINEER;

-- ---------------------------------------------------------------------------
-- 3. Database-level access grants
--    "ALL ..."    covers objects that exist now (your current tables and data)
--    "FUTURE ..." covers objects created later, so new tables need no re-grant
--    SECURITYADMIN holds MANAGE GRANTS, so it can grant on objects it doesn't own.
-- ---------------------------------------------------------------------------

-- READ: see the database and every schema in it...
GRANT USAGE ON DATABASE DATATHON_TEST                         TO ROLE DTH_DB_READ;
GRANT USAGE ON ALL SCHEMAS IN DATABASE DATATHON_TEST          TO ROLE DTH_DB_READ;
GRANT USAGE ON FUTURE SCHEMAS IN DATABASE DATATHON_TEST       TO ROLE DTH_DB_READ;
-- ...and SELECT from every table and view, now and later.
GRANT SELECT ON ALL TABLES IN DATABASE DATATHON_TEST          TO ROLE DTH_DB_READ;
GRANT SELECT ON FUTURE TABLES IN DATABASE DATATHON_TEST       TO ROLE DTH_DB_READ;
GRANT SELECT ON ALL VIEWS IN DATABASE DATATHON_TEST           TO ROLE DTH_DB_READ;
GRANT SELECT ON FUTURE VIEWS IN DATABASE DATATHON_TEST        TO ROLE DTH_DB_READ;
-- Dynamic tables and materialized views are separate object types in
-- Snowflake: the TABLES and VIEWS grants above do NOT cover them. The agent
-- publishes dynamic tables, so read access to them must be granted explicitly.
GRANT SELECT ON ALL DYNAMIC TABLES IN DATABASE DATATHON_TEST       TO ROLE DTH_DB_READ;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN DATABASE DATATHON_TEST    TO ROLE DTH_DB_READ;
GRANT SELECT ON ALL MATERIALIZED VIEWS IN DATABASE DATATHON_TEST    TO ROLE DTH_DB_READ;
GRANT SELECT ON FUTURE MATERIALIZED VIEWS IN DATABASE DATATHON_TEST TO ROLE DTH_DB_READ;

-- WRITE: add, change, delete and empty rows in every table, now and later.
GRANT INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN DATABASE DATATHON_TEST    TO ROLE DTH_DB_WRITE;
GRANT INSERT, UPDATE, DELETE, TRUNCATE ON FUTURE TABLES IN DATABASE DATATHON_TEST TO ROLE DTH_DB_WRITE;
-- WRITE: run the stored procedures and functions the team writes (Snowpark parsing etc.).
GRANT USAGE ON ALL PROCEDURES IN DATABASE DATATHON_TEST       TO ROLE DTH_DB_WRITE;
GRANT USAGE ON FUTURE PROCEDURES IN DATABASE DATATHON_TEST    TO ROLE DTH_DB_WRITE;
GRANT USAGE ON ALL FUNCTIONS IN DATABASE DATATHON_TEST        TO ROLE DTH_DB_WRITE;
GRANT USAGE ON FUTURE FUNCTIONS IN DATABASE DATATHON_TEST     TO ROLE DTH_DB_WRITE;

-- BUILD: see refresh history of dynamic tables (MONITOR) and suspend,
-- resume or refresh them (OPERATE), e.g. to force the agent's data to update.
GRANT MONITOR, OPERATE ON ALL DYNAMIC TABLES IN DATABASE DATATHON_TEST    TO ROLE DTH_DB_BUILD;
GRANT MONITOR, OPERATE ON FUTURE DYNAMIC TABLES IN DATABASE DATATHON_TEST TO ROLE DTH_DB_BUILD;

-- BUILD: create new schemas in the database...
GRANT CREATE SCHEMA ON DATABASE DATATHON_TEST TO ROLE DTH_DB_BUILD;
-- ...and create objects inside every existing and future schema.
-- (CREATE DYNAMIC TABLE lets the team build its own dynamic tables on top of the agent's.)
GRANT CREATE TABLE, CREATE VIEW, CREATE DYNAMIC TABLE, CREATE STAGE, CREATE FILE FORMAT,
      CREATE SEQUENCE, CREATE FUNCTION, CREATE PROCEDURE, CREATE STREAMLIT
  ON ALL SCHEMAS IN DATABASE DATATHON_TEST TO ROLE DTH_DB_BUILD;
GRANT CREATE TABLE, CREATE VIEW, CREATE DYNAMIC TABLE, CREATE STAGE, CREATE FILE FORMAT,
      CREATE SEQUENCE, CREATE FUNCTION, CREATE PROCEDURE, CREATE STREAMLIT
  ON FUTURE SCHEMAS IN DATABASE DATATHON_TEST TO ROLE DTH_DB_BUILD;


-- ---------------------------------------------------------------------------
-- 3b. MART: the only schema the Data Analyst, PM and app can read
-- ---------------------------------------------------------------------------

-- Create the schema for masked secure views (built in script 03).
-- SYSADMIN owns it, so the team (not the agent) controls it.
USE ROLE SYSADMIN;
CREATE SCHEMA IF NOT EXISTS DATATHON_TEST.MART COMMENT = 'Masked secure views for dashboard and app';

USE ROLE SECURITYADMIN;
-- MART_READ: see the database and the MART schema only...
GRANT USAGE ON DATABASE DATATHON_TEST        TO ROLE DTH_MART_READ;
GRANT USAGE ON SCHEMA DATATHON_TEST.MART     TO ROLE DTH_MART_READ;
-- ...and SELECT on the views in MART. Deliberately "ALL" (existing views),
-- not "FUTURE": a schema-level future grant would override the database-level
-- future grants above for MART. Script 03 reruns this after creating views.
GRANT SELECT ON ALL VIEWS IN SCHEMA DATATHON_TEST.MART TO ROLE DTH_MART_READ;

-- ---------------------------------------------------------------------------
-- 4. Team roles <- access levels (THIS is who can do what)
--
--   Role                 Access         Sees individual names?
--   Data Engineer        BUILD          yes (COURTLENS raw data and MART)
--   Analytics Engineer   BUILD          yes
--   Data Scientist       WRITE          yes
--   Data Analyst         MART + app     no (masked views only)
--   Project Manager      MART  + Build  (as building the roles and responsibilites) can view and build as playing role of cloud engineer
--   Cloud Engineer       BUILD          in COURTLENS yes; in MART views masked
--   Pipeline service     WRITE          yes (only if a separate Lambda job writes data)
--   INGESTIONAGENT       unchanged      (owns the agent's objects)
--   App viewer           app only       no
-- ---------------------------------------------------------------------------

-- Data Engineer: loads and parses documents, so may create tables and stages.
GRANT ROLE DTH_DB_BUILD   TO ROLE DTH_DATA_ENGINEER;
-- Analytics Engineer: builds the model and views, so may create objects.
GRANT ROLE DTH_DB_BUILD   TO ROLE DTH_ANALYTICS_ENGINEER;
-- Data Scientist: writes extraction results, but doesn't change structure.
GRANT ROLE DTH_DB_WRITE   TO ROLE DTH_DATA_SCIENTIST;
-- Data Analyst: reads the masked MART views only...
GRANT ROLE DTH_MART_READ  TO ROLE DTH_DATA_ANALYST;
-- ...and may create the Streamlit app in MART (the app needs a stage for its files).
GRANT CREATE STREAMLIT, CREATE STAGE ON SCHEMA DATATHON_TEST.MART TO ROLE DTH_DATA_ANALYST;
-- Project Manager: masked MART views only, plus app viewing.
GRANT ROLE DTH_MART_READ  TO ROLE DTH_PROJECT_MANAGER;
GRANT ROLE DTH_APP_VIEWER TO ROLE DTH_PROJECT_MANAGER;
GRANT ROLE DTH_DB_BUILD   TO ROLE DTH_PROJECT_MANAGER;

-- ONLY if you already ran an EARLIER version of this script: it gave the
-- Data Analyst and PM database-wide read (unmasked COURTLENS). Take it back:
-- REVOKE ROLE DTH_DB_READ FROM ROLE DTH_DATA_ANALYST;
-- REVOKE ROLE DTH_DB_READ FROM ROLE DTH_PROJECT_MANAGER;
-- REVOKE CREATE STREAMLIT, CREATE STAGE ON SCHEMA DATATHON_TEST.COURTLENS FROM ROLE DTH_DATA_ANALYST;

-- Cloud Engineer: full build rights for fixes and deploys.
GRANT ROLE DTH_DB_BUILD   TO ROLE DTH_CLOUD_ENGINEER;
-- Pipeline service: reads text and writes results; no structure changes.
GRANT ROLE DTH_DB_WRITE   TO ROLE DTH_PIPELINE_SVC;
-- App viewers: only see the database and MART, enough to open the app
-- (USAGE on the app itself is granted in 03 once it exists).
GRANT USAGE ON DATABASE DATATHON_TEST TO ROLE DTH_APP_VIEWER;
GRANT USAGE ON SCHEMA DATATHON_TEST.MART TO ROLE DTH_APP_VIEWER;

-- "See real names" capability: only roles that must check names against source text.
GRANT ROLE DTH_PII_READER TO ROLE DTH_DATA_ENGINEER;
GRANT ROLE DTH_PII_READER TO ROLE DTH_DATA_ANALYST;
GRANT ROLE DTH_PII_READER TO ROLE DTH_ANALYTICS_ENGINEER;
GRANT ROLE DTH_PII_READER TO ROLE DTH_DATA_SCIENTIST;
GRANT ROLE DTH_PII_READER TO ROLE DTH_PIPELINE_SVC;

-- Snowflake's built-in LLM functions (Cortex), our Bedrock fallback.
USE ROLE ACCOUNTADMIN;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE DTH_DATA_SCIENTIST;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE DTH_PIPELINE_SVC;
-- Cost and query history: CE sees both, PM sees cost only.
GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE DTH_CLOUD_ENGINEER;
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER      TO ROLE DTH_CLOUD_ENGINEER;
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER      TO ROLE DTH_PROJECT_MANAGER;
GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE DTH_PROJECT_MANAGER;


-- ---------------------------------------------------------------------------
-- 5. Give each teammate their role (use login names from SHOW USERS in 01)
-- ---------------------------------------------------------------------------
USE ROLE SECURITYADMIN;

--SHOW USERS;

-- Replace each <..._USER> with the teammate's login name, then run.
GRANT ROLE DTH_PROJECT_MANAGER    TO USER ASOO584;
GRANT ROLE DTH_CLOUD_ENGINEER     TO USER ASOO584;
GRANT ROLE DTH_DATA_ENGINEER      TO USER ESAM570;
GRANT ROLE DTH_DATA_ENGINEER      TO USER SLIN567;
GRANT ROLE DTH_ANALYTICS_ENGINEER TO USER GREGORYHINDS;
--GRANT ROLE DTH_DATA_SCIENTIST     TO USER DS_USER;
GRANT ROLE DTH_DATA_ANALYST       TO USER RREZ269;
GRANT ROLE DTH_CLOUD_ENGINEER     TO USER RREZ269;

