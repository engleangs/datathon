{#- Use the schema name exactly as configured (STAGING, MARTS).
    Default dbt behaviour would give STAGING_STAGING. Environments are
    separated by database (NZDC_DEV / NZDC_PROD), not by schema prefix. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim | upper }}
    {%- endif -%}
{%- endmacro %}
