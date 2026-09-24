-- 01  DISCOVER: read-only checks before changing anything.

-- using most powerful role to  every SHOW command can see everything.
USE ROLE ACCOUNTADMIN;

-- Confirm if I'm in the right account
SELECT CURRENT_USER(), CURRENT_ACCOUNT(), CURRENT_ROLE();

-- owner of DATATHON_TEST?
SHOW DATABASES LIKE 'DATATHON_TEST';

-- Every schema in the database, with its owner
SHOW SCHEMAS IN DATABASE DATATHON_TEST;

-- Every table in COURTLENS, with row counts and owner.
SHOW TABLES IN SCHEMA DATATHON_TEST.COURTLENS;

-- creates the warehouse neexded to run below select queries
CREATE WAREHOUSE IF NOT EXISTS DTH_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
USE WAREHOUSE DTH_WH;

-- The columns of every COURTLENS table. Find the column holding party names.
SELECT table_name, column_name, data_type, character_maximum_length
FROM DATATHON_TEST.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = 'COURTLENS'
ORDER BY table_name, ordinal_position;

-- Text columns with length 1 are a sign of the CHAR problem from the ERD - I found no chars which was good
-- (names cut to one letter). 
SELECT table_name, column_name, data_type, character_maximum_length
FROM DATATHON_TEST.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = 'COURTLENS' AND data_type = 'TEXT' AND character_maximum_length = 1;

-- Stages (where PDFs live) anywhere in the database. Note their names.
SHOW STAGES IN DATABASE DATATHON_TEST;

-- Existing warehouses, so you know what compute is already running.
SHOW WAREHOUSES;

-- All users. Note each teammate's login name (the "name" column).
SHOW USERS;

-- Existing roles, so we don't clash with anything the organisers created.
SHOW ROLES;

-- Schema-level future grants override database-level ones in that schema.
-- If this returns rows for COURTLENS, tell the team: they win over script 02.
SHOW FUTURE GRANTS IN SCHEMA DATATHON_TEST.COURTLENS;

-- Future grants already defined for the whole database.
SHOW FUTURE GRANTS IN DATABASE DATATHON_TEST;


SHOW STAGES IN ACCOUNT;



