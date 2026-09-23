#!/usr/bin/env bash
# Deploy everything for one environment. Used locally and by CI.
#   ./scripts/deploy.sh dev
#   ./scripts/deploy.sh prod
# Needs: terraform, snow (Snowflake CLI), dbt-snowflake, AWS credentials,
#        and a Snowflake CLI connection named "nzdc" (see README).
set -euo pipefail

ENV="${1:-dev}"
ENV_UPPER="$(echo "$ENV" | tr '[:lower:]' '[:upper:]')"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/build/sql_$ENV"
mkdir -p "$BUILD"

echo "== 1/4 Terraform ($ENV)"
terraform -chdir="$ROOT/terraform" init -input=false
terraform -chdir="$ROOT/terraform" workspace select -or-create "$ENV"
terraform -chdir="$ROOT/terraform" apply -input=false -auto-approve -var="env=$ENV"
API_URL="$(terraform -chdir="$ROOT/terraform" output -raw bedrock_api_url)"

echo "== 2/4 Render SQL for NZDC_$ENV_UPPER"
for f in "$ROOT"/sql/0[1-3]_*.sql; do
  sed -e "s/NZDC_DEV/NZDC_${ENV_UPPER}/g" \
      -e "s#<BEDROCK_API_URL>#${API_URL}#g" \
      "$f" > "$BUILD/$(basename "$f")"
done

echo "== 3/4 Snowflake objects (function, tables, procedure, task)"
snow sql -c nzdc -f "$BUILD/01_bedrock_function.sql"
snow sql -c nzdc -f "$BUILD/02_pipeline.sql"
# 03_monitoring.sql has ACCOUNTADMIN parts: run it once by hand, not in CI.

echo "== 4/4 dbt build"
cd "$ROOT/dbt"
dbt deps
dbt seed   --target "$ENV" --profiles-dir .
dbt build  --target "$ENV" --profiles-dir . --exclude "resource_type:seed"

echo "Deployed $ENV."
