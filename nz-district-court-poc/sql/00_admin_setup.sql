-- =====================================================================
-- 00_admin_setup.sql
-- Run ONCE as ACCOUNTADMIN, BEFORE terraform apply.
-- Terraform cannot (or should not) own these account-level settings.
-- =====================================================================
USE ROLE ACCOUNTADMIN;

-- 1. Service user for Terraform (key-pair auth, no password).
--    Generate the key:  openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -out snowflake_tf_key.p8
--                       openssl rsa -in snowflake_tf_key.p8 -pubout -out snowflake_tf_key.pub
CREATE USER IF NOT EXISTS TERRAFORM_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = ACCOUNTADMIN
  COMMENT = 'Terraform for nz-judgments-poc';
-- ALTER USER TERRAFORM_SVC SET RSA_PUBLIC_KEY = '<paste public key body, no header lines>';
GRANT ROLE ACCOUNTADMIN TO USER TERRAFORM_SVC;

-- 2. Service user for the pipeline, dbt CI and the upload script.
CREATE USER IF NOT EXISTS NZDC_PIPELINE_SVC
  TYPE = SERVICE
  COMMENT = 'Runs Cortex pipeline and dbt in CI';
-- ALTER USER NZDC_PIPELINE_SVC SET RSA_PUBLIC_KEY = '<...>';
-- After terraform apply:
-- GRANT ROLE NZDC_DEV_PIPELINE    TO USER NZDC_PIPELINE_SVC;
-- GRANT ROLE NZDC_DEV_TRANSFORMER TO USER NZDC_PIPELINE_SVC;

-- 3. Cortex access is RBAC-controlled. By default PUBLIC has CORTEX_USER.
--    Revoke it, so only the pipeline role (granted in Terraform) can call AI functions.
REVOKE DATABASE ROLE SNOWFLAKE.CORTEX_USER FROM ROLE PUBLIC;

-- 4. Many Cortex models are not hosted in ap-southeast-2 (Sydney).
--    Cross-region inference lets calls route to a region that has the model.
--    Data leaves the region for inference. Note this in your design doc.
ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION';

-- 5. Optional but good practice: restrict which Cortex models the account may use.
-- ALTER ACCOUNT SET CORTEX_MODELS_ALLOWLIST = 'mistral-large2,llama3.1-70b,claude-sonnet-4-5';
