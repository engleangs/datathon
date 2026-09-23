output "s3_bucket" {
  value = aws_s3_bucket.docs.bucket
}

output "bedrock_api_url" {
  description = "Paste into sql/03_bedrock.sql as the external function URL."
  value       = "${aws_api_gateway_stage.v1.invoke_url}/summarise"
}

output "snowflake_database" {
  value = snowflake_database.main.name
}

output "snowflake_warehouse" {
  value = snowflake_warehouse.wh.name
}

output "snowflake_roles" {
  value = {
    pipeline    = snowflake_account_role.pipeline.name
    transformer = snowflake_account_role.transformer.name
    analyst     = snowflake_account_role.analyst.name
  }
}

output "api_integration" {
  value = snowflake_api_integration.bedrock.name
}
