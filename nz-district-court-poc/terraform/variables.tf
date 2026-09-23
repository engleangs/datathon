variable "project" {
  description = "Short name. Used as a prefix for all objects."
  type        = string
  default     = "nzdc"
}

variable "owner" {
  description = "Tag value for AWS resources."
  type        = string
  default     = "simon"
}

variable "env" {
  description = "Environment name: dev or prod. Goes into object names."
  type        = string
  default     = "dev"
}

# ---------- AWS ----------
variable "aws_region" {
  description = "AWS region. Use the same region as your Snowflake account to avoid egress cost."
  type        = string
  default     = "ap-southeast-2"
}

variable "bedrock_model_id" {
  description = "Bedrock model or inference profile ID. Check the Bedrock console for the IDs your account can use."
  type        = string
  default     = "anthropic.claude-sonnet-4-20250514-v1:0"
}

variable "aws_monthly_budget_usd" {
  description = "AWS budget alert threshold in USD."
  type        = number
  default     = 20
}

variable "budget_alert_email" {
  description = "Email for AWS budget alerts and the Snowflake resource monitor."
  type        = string
}

# ---------- Snowflake ----------
variable "snowflake_organization" {
  type = string
}

variable "snowflake_account" {
  type = string
}

variable "snowflake_user" {
  description = "Admin user that Terraform runs as (key-pair auth)."
  type        = string
}

variable "snowflake_private_key_path" {
  type = string
}

variable "snowflake_monthly_credit_quota" {
  description = "Credit quota for the resource monitor on the shared warehouse."
  type        = number
  default     = 20
}

variable "analyst_users" {
  description = "Existing Snowflake users that get the ANALYST role."
  type        = list(string)
  default     = []
}
