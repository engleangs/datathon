terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 2.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Local state is fine for a solo trial.
  # For CI, create an S3 bucket once by hand, then uncomment this block.
  # backend "s3" {
  #   bucket = "your-tf-state-bucket"
  #   key    = "nz-judgments-poc/terraform.tfstate"
  #   region = "ap-southeast-2"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      project = var.project
      owner   = var.owner
    }
  }
}

provider "snowflake" {
  organization_name = var.snowflake_organization
  account_name      = var.snowflake_account
  user              = var.snowflake_user
  role              = "ACCOUNTADMIN"
  authenticator     = "SNOWFLAKE_JWT"
  private_key       = file(var.snowflake_private_key_path)

  # These resources are "preview" in provider v2.x.
  # Check the provider changelog if terraform plan complains.
  preview_features_enabled = [
    "snowflake_storage_integration_resource",
    "snowflake_api_integration_resource",
    "snowflake_stage_resource",
  ]
}

data "aws_caller_identity" "current" {}
