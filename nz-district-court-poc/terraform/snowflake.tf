locals {
  sf_prefix = upper("${var.project}_${var.env}")   # e.g. NZDC_DEV
  db_name   = local.sf_prefix
  schemas   = ["RAW", "STAGING", "MARTS", "OPS"]
}

# =====================================================================
# Database and schemas
# =====================================================================
resource "snowflake_database" "main" {
  name    = local.db_name
  comment = "District Court of NZ decisions: documents to structured insights PoC"
}

resource "snowflake_schema" "s" {
  for_each = toset(local.schemas)
  database = snowflake_database.main.name
  name     = each.key
}

# =====================================================================
# Warehouse: ONE shared XS warehouse for load, AI and dbt.
# Separation is done with roles and query tags, not extra warehouses.
# =====================================================================
resource "snowflake_resource_monitor" "wh" {
  name            = "${local.sf_prefix}_RM"
  credit_quota    = var.snowflake_monthly_credit_quota
  frequency       = "MONTHLY"
  start_timestamp = "IMMEDIATELY"

  notify_triggers           = [50, 80]
  suspend_trigger           = 100
  suspend_immediate_trigger = 110
}

resource "snowflake_warehouse" "wh" {
  name                = "${local.sf_prefix}_WH"
  warehouse_size      = "XSMALL"
  auto_suspend        = 60
  auto_resume         = "true"
  initially_suspended = true
  resource_monitor    = snowflake_resource_monitor.wh.name
  comment             = "Shared by pipeline, dbt and analysts. Scale up only for backfills."
}

# =====================================================================
# Integrations and external stage
# =====================================================================
resource "snowflake_storage_integration" "s3" {
  name                      = "${local.sf_prefix}_S3_INT"
  type                      = "EXTERNAL_STAGE"
  enabled                   = true
  storage_provider          = "S3"
  storage_aws_role_arn      = local.s3_role_arn
  storage_allowed_locations = ["s3://${aws_s3_bucket.docs.bucket}/"]
}

resource "snowflake_stage" "judgments" {
  name                = "JUDGMENTS_STAGE"
  database            = snowflake_database.main.name
  schema              = snowflake_schema.s["RAW"].name
  url                 = "s3://${aws_s3_bucket.docs.bucket}/judgments/"
  storage_integration = snowflake_storage_integration.s3.name
  # Directory table lists files. AI functions read files through TO_FILE().
  # SSE (server-side) encryption is needed for AI_PARSE_DOCUMENT on S3 stages.
  directory  = "ENABLE = true"
  encryption = "TYPE = 'AWS_SSE_S3'"
  depends_on = [aws_iam_role_policy.snowflake_s3_read]
}

resource "snowflake_api_integration" "bedrock" {
  name                 = "${local.sf_prefix}_BEDROCK_API_INT"
  api_provider         = "aws_api_gateway"
  api_aws_role_arn     = local.api_role_arn
  api_allowed_prefixes = ["https://${aws_api_gateway_rest_api.bedrock.id}.execute-api.${var.aws_region}.amazonaws.com/"]
  enabled              = true
}

# =====================================================================
# RBAC: privileges -> DATABASE roles -> ACCOUNT roles -> users
# =====================================================================

# ---- Database roles (hold object privileges; live inside the database) ----
resource "snowflake_database_role" "raw_rw" {
  database = snowflake_database.main.name
  name     = "RAW_RW"
  comment  = "Create and write objects in RAW and OPS. Read the judgments stage."
}

resource "snowflake_database_role" "analytics_rw" {
  database = snowflake_database.main.name
  name     = "ANALYTICS_RW"
  comment  = "Read RAW. Build models in STAGING and MARTS (dbt)."
}

resource "snowflake_database_role" "analytics_r" {
  database = snowflake_database.main.name
  name     = "ANALYTICS_R"
  comment  = "Read MARTS only."
}

# Database usage for every database role
resource "snowflake_grant_privileges_to_database_role" "db_usage" {
  for_each = {
    raw_rw       = snowflake_database_role.raw_rw.fully_qualified_name
    analytics_rw = snowflake_database_role.analytics_rw.fully_qualified_name
    analytics_r  = snowflake_database_role.analytics_r.fully_qualified_name
  }
  database_role_name = each.value
  privileges         = ["USAGE"]
  on_database        = snowflake_database.main.name
}

# RAW_RW: build in RAW and OPS
resource "snowflake_grant_privileges_to_database_role" "raw_rw_schemas" {
  for_each           = toset(["RAW", "OPS"])
  database_role_name = snowflake_database_role.raw_rw.fully_qualified_name
  privileges = [
    "USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE STREAM",
    "CREATE TASK", "CREATE FUNCTION", "CREATE PROCEDURE", "CREATE MASKING POLICY",
  ]
  on_schema {
    schema_name = snowflake_schema.s[each.key].fully_qualified_name
  }
}

# The pipeline role owns the stage, so it can run ALTER STAGE ... REFRESH
# on the directory table. ACCOUNTADMIN still sees it through the role hierarchy.
resource "snowflake_grant_ownership" "stage_to_pipeline" {
  account_role_name   = snowflake_account_role.pipeline.name
  outbound_privileges = "COPY"
  on {
    object_type = "STAGE"
    object_name = snowflake_stage.judgments.fully_qualified_name
  }
  depends_on = [snowflake_grant_privileges_to_account_role.pipeline_int]
}

# ANALYTICS_RW: read RAW, build in STAGING and MARTS.
# USAGE on OPS lets dbt attach the masking policy that lives there.
resource "snowflake_grant_privileges_to_database_role" "analytics_rw_raw_usage" {
  for_each           = toset(["RAW", "OPS"])
  database_role_name = snowflake_database_role.analytics_rw.fully_qualified_name
  privileges         = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.s[each.key].fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_database_role" "analytics_rw_raw_future_select" {
  for_each           = toset(["TABLES", "VIEWS"])
  database_role_name = snowflake_database_role.analytics_rw.fully_qualified_name
  privileges         = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = each.key
      in_schema          = snowflake_schema.s["RAW"].fully_qualified_name
    }
  }
}

resource "snowflake_grant_privileges_to_database_role" "analytics_rw_build" {
  for_each           = toset(["STAGING", "MARTS"])
  database_role_name = snowflake_database_role.analytics_rw.fully_qualified_name
  privileges         = ["USAGE", "CREATE TABLE", "CREATE VIEW", "CREATE STREAMLIT", "CREATE STAGE"]
  on_schema {
    schema_name = snowflake_schema.s[each.key].fully_qualified_name
  }
}

# ANALYTICS_R: read MARTS
resource "snowflake_grant_privileges_to_database_role" "analytics_r_marts_usage" {
  database_role_name = snowflake_database_role.analytics_r.fully_qualified_name
  privileges         = ["USAGE"]
  on_schema {
    schema_name = snowflake_schema.s["MARTS"].fully_qualified_name
  }
}

resource "snowflake_grant_privileges_to_database_role" "analytics_r_marts_future" {
  for_each           = toset(["TABLES", "VIEWS"])
  database_role_name = snowflake_database_role.analytics_r.fully_qualified_name
  privileges         = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = each.key
      in_schema          = snowflake_schema.s["MARTS"].fully_qualified_name
    }
  }
}

# The dbt role also reads MARTS
resource "snowflake_grant_database_role" "analytics_r_to_rw" {
  database_role_name        = snowflake_database_role.analytics_r.fully_qualified_name
  parent_database_role_name = snowflake_database_role.analytics_rw.fully_qualified_name
}

# ---- Account roles (functional roles that users and services get) ----
resource "snowflake_account_role" "pipeline" {
  name    = "${local.sf_prefix}_PIPELINE"
  comment = "Service role: document ingest, Cortex extraction, Bedrock calls, tasks."
}

resource "snowflake_account_role" "transformer" {
  name    = "${local.sf_prefix}_TRANSFORMER"
  comment = "Service role for dbt (local and CI)."
}

resource "snowflake_account_role" "analyst" {
  name    = "${local.sf_prefix}_ANALYST"
  comment = "Human read-only role for marts and the Streamlit app."
}

# Database role -> account role
resource "snowflake_grant_database_role" "raw_rw_to_pipeline" {
  database_role_name = snowflake_database_role.raw_rw.fully_qualified_name
  parent_role_name   = snowflake_account_role.pipeline.name
}

resource "snowflake_grant_database_role" "analytics_rw_to_transformer" {
  database_role_name = snowflake_database_role.analytics_rw.fully_qualified_name
  parent_role_name   = snowflake_account_role.transformer.name
}

resource "snowflake_grant_database_role" "analytics_r_to_analyst" {
  database_role_name = snowflake_database_role.analytics_r.fully_qualified_name
  parent_role_name   = snowflake_account_role.analyst.name
}

# Cortex AI functions: only the pipeline role may call them.
# (Revoke SNOWFLAKE.CORTEX_USER from PUBLIC once, by hand, so this grant means something.)
resource "snowflake_grant_database_role" "cortex_to_pipeline" {
  database_role_name = "\"SNOWFLAKE\".\"CORTEX_USER\""
  parent_role_name   = snowflake_account_role.pipeline.name
}

# Warehouse usage for all three account roles
resource "snowflake_grant_privileges_to_account_role" "wh_usage" {
  for_each = {
    pipeline    = snowflake_account_role.pipeline.name
    transformer = snowflake_account_role.transformer.name
    analyst     = snowflake_account_role.analyst.name
  }
  account_role_name = each.value
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.wh.name
  }
}

# Pipeline role: integrations and task execution
resource "snowflake_grant_privileges_to_account_role" "pipeline_int" {
  for_each = {
    s3      = snowflake_storage_integration.s3.name
    bedrock = snowflake_api_integration.bedrock.name
  }
  account_role_name = snowflake_account_role.pipeline.name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "INTEGRATION"
    object_name = each.value
  }
}

resource "snowflake_grant_privileges_to_account_role" "pipeline_execute_task" {
  account_role_name = snowflake_account_role.pipeline.name
  privileges        = ["EXECUTE TASK"]
  on_account        = true
}

# Role hierarchy: everything rolls up to SYSADMIN
resource "snowflake_grant_account_role" "to_sysadmin" {
  for_each = {
    pipeline    = snowflake_account_role.pipeline.name
    transformer = snowflake_account_role.transformer.name
    analyst     = snowflake_account_role.analyst.name
  }
  role_name        = each.value
  parent_role_name = "SYSADMIN"
}

# Analyst role to named users
resource "snowflake_grant_account_role" "analyst_users" {
  for_each  = toset(var.analyst_users)
  role_name = snowflake_account_role.analyst.name
  user_name = each.key
}
