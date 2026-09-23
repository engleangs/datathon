CREATE ROLE IF NOT EXISTS IngestionAgent
    COMMENT = 'Service role for the court document ingestion tool: read + insert on COURT_DOCS';

-- Makes SYSADMIN inherit the role, so admins can see and manage what it uses
GRANT ROLE IngestionAgent TO ROLE SYSADMIN;
USE ROLE SECURITYADMIN;

-- Compute: without this, the role can't run any query
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE IngestionAgent;

-- Access to the database and schema
GRANT USAGE ON DATABASE datathon_test                TO ROLE IngestionAgent;
GRANT USAGE ON SCHEMA datathon_test.courtlens       TO ROLE IngestionAgent;


-- Read + insert on existing tables, and on any tables created later
GRANT SELECT, INSERT ON ALL TABLES    IN SCHEMA datathon_test.courtlens TO ROLE IngestionAgent;
GRANT SELECT, INSERT ON FUTURE TABLES IN SCHEMA datathon_test.courtlens TO ROLE IngestionAgent;

-- 3. A service user for the tool to log in as (key-pair auth, no password)
USE ROLE USERADMIN;
CREATE USER IF NOT EXISTS INGESTION_AGENT_SVC
    TYPE                 = LEGACY_SERVICE
    PASSWORD             = 'P?QAoBg&LNAK694L'
    MUST_CHANGE_PASSWORD = FALSE          -- a bot can't respond to a forced reset
    DEFAULT_ROLE      = IngestionAgent
    DEFAULT_WAREHOUSE = COMPUTE_WH
    DEFAULT_NAMESPACE = datathon_test.courtlens
    COMMENT = 'Login for the court document ingestion tool';

USE ROLE SECURITYADMIN;
GRANT ROLE IngestionAgent TO USER INGESTION_AGENT_SVC;  -- DEFAULT_ROLE alone doesn't grant it

-- 4. Check the result
SHOW GRANTS TO ROLE IngestionAgent;
SHOW FUTURE GRANTS IN SCHEMA datathon_test.courtlens