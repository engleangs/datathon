locals {
  prefix = "${var.project}-${var.env}"

  # Role names are fixed up front. This breaks the circular dependency:
  # Snowflake needs the role ARN, and the role trust policy needs Snowflake's IAM user.
  s3_role_name  = "${local.prefix}-snowflake-s3"
  api_role_name = "${local.prefix}-snowflake-api"
  s3_role_arn   = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.s3_role_name}"
  api_role_arn  = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.api_role_name}"
}

# =====================================================================
# S3 landing bucket for judgment PDFs
# =====================================================================
resource "aws_s3_bucket" "docs" {
  bucket        = "${local.prefix}-judgments-${data.aws_caller_identity.current.account_id}"
  force_destroy = true # PoC only. Lets terraform destroy empty the bucket.
}

resource "aws_s3_bucket_public_access_block" "docs" {
  bucket                  = aws_s3_bucket.docs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "docs" {
  bucket = aws_s3_bucket.docs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# IAM role that Snowflake assumes to read the bucket (read-only).
resource "aws_iam_role" "snowflake_s3" {
  name = local.s3_role_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = snowflake_storage_integration.s3.storage_aws_iam_user_arn }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = snowflake_storage_integration.s3.storage_aws_external_id }
      }
    }]
  })
}

resource "aws_iam_role_policy" "snowflake_s3_read" {
  name = "read-judgments"
  role = aws_iam_role.snowflake_s3.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:GetObjectVersion"]
        Resource = "${aws_s3_bucket.docs.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetBucketLocation"]
        Resource = aws_s3_bucket.docs.arn
      }
    ]
  })
}

# =====================================================================
# Bedrock via Lambda + API Gateway, called from Snowflake as an external function
# =====================================================================
data "archive_file" "bedrock_lambda" {
  type        = "zip"
  source_file = "${path.module}/../lambda/bedrock_summarise.py"
  output_path = "${path.module}/build/bedrock_summarise.zip"
}

resource "aws_iam_role" "lambda" {
  name = "${local.prefix}-bedrock-lambda"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_bedrock" {
  name = "invoke-bedrock"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["bedrock:InvokeModel", "bedrock:Converse"]
      # Tighten to the exact model / inference-profile ARN once you pick one.
      Resource = "*"
    }]
  })
}

resource "aws_lambda_function" "bedrock" {
  function_name    = "${local.prefix}-bedrock-summarise"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "bedrock_summarise.handler"
  filename         = data.archive_file.bedrock_lambda.output_path
  source_code_hash = data.archive_file.bedrock_lambda.output_base64sha256
  timeout          = 120
  memory_size      = 256
  # Caps parallel Bedrock calls. Protects both cost and Bedrock quotas.
  reserved_concurrent_executions = 5

  environment {
    variables = {
      MODEL_ID   = var.bedrock_model_id
      MAX_TOKENS = "1500"
    }
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.bedrock.function_name}"
  retention_in_days = 14
}

# --- API Gateway (REST, regional, IAM auth) ---
resource "aws_api_gateway_rest_api" "bedrock" {
  name = "${local.prefix}-bedrock-api"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "summarise" {
  rest_api_id = aws_api_gateway_rest_api.bedrock.id
  parent_id   = aws_api_gateway_rest_api.bedrock.root_resource_id
  path_part   = "summarise"
}

resource "aws_api_gateway_method" "post" {
  rest_api_id   = aws_api_gateway_rest_api.bedrock.id
  resource_id   = aws_api_gateway_resource.summarise.id
  http_method   = "POST"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "lambda" {
  rest_api_id             = aws_api_gateway_rest_api.bedrock.id
  resource_id             = aws_api_gateway_resource.summarise.id
  http_method             = aws_api_gateway_method.post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.bedrock.invoke_arn
  # 29 s is the default API Gateway limit. For long judgments, request a quota
  # increase ("Maximum integration timeout") and raise this value.
  timeout_milliseconds = 29000
}

resource "aws_api_gateway_deployment" "bedrock" {
  rest_api_id = aws_api_gateway_rest_api.bedrock.id
  triggers = {
    redeploy = sha1(jsonencode([
      aws_api_gateway_resource.summarise.id,
      aws_api_gateway_method.post.id,
      aws_api_gateway_integration.lambda.id,
      aws_api_gateway_rest_api_policy.bedrock.policy,
    ]))
  }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "v1" {
  rest_api_id   = aws_api_gateway_rest_api.bedrock.id
  deployment_id = aws_api_gateway_deployment.bedrock.id
  stage_name    = "v1"
}

resource "aws_api_gateway_method_settings" "throttle" {
  rest_api_id = aws_api_gateway_rest_api.bedrock.id
  stage_name  = aws_api_gateway_stage.v1.stage_name
  method_path = "*/*"
  settings {
    throttling_rate_limit  = 5
    throttling_burst_limit = 10
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.bedrock.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.bedrock.execution_arn}/*/POST/summarise"
}

# Only the Snowflake API role may call the endpoint.
resource "aws_api_gateway_rest_api_policy" "bedrock" {
  rest_api_id = aws_api_gateway_rest_api.bedrock.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = "arn:aws:sts::${data.aws_caller_identity.current.account_id}:assumed-role/${local.api_role_name}/snowflake" }
      Action    = "execute-api:Invoke"
      Resource  = "${aws_api_gateway_rest_api.bedrock.execution_arn}/*/POST/summarise"
    }]
  })
}

# IAM role that Snowflake assumes to call API Gateway.
resource "aws_iam_role" "snowflake_api" {
  name = local.api_role_name
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = snowflake_api_integration.bedrock.api_aws_iam_user_arn }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = snowflake_api_integration.bedrock.api_aws_external_id }
      }
    }]
  })
}

# =====================================================================
# AWS budget (cost guardrail on the AWS side)
# =====================================================================
resource "aws_budgets_budget" "monthly" {
  name         = "${local.prefix}-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.aws_monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    # Activate "project" as a cost allocation tag in Billing first.
    values = [format("user:project$%s", var.project)]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_alert_email]
  }
}
