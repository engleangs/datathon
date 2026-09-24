{#
    Shared text helpers, so dimension keys are built identically in every model.
#}

{# Trim, collapse internal whitespace, and turn empty strings into NULL. #}
{% macro clean_text(expr) -%}
    nullif(trim(regexp_replace({{ expr }}, '\\s+', ' ')), '')
{%- endmacro %}


{# Stable key for a name-based dimension: case- and whitespace-insensitive. NULL in, NULL out. #}
{% macro name_key(expr) -%}
    md5(lower({{ clean_text(expr) }}))
{%- endmacro %}


{# Stable key for a combination of columns (used for bridge / detail rows). #}
{% macro surrogate_key(columns) -%}
    md5(
    {%- for col in columns -%}
        coalesce(cast({{ col }} as varchar), '_null_')
        {%- if not loop.last %} || '|' || {% endif -%}
    {%- endfor -%}
    )
{%- endmacro %}
