{#- Turn "2 years and 6 months' imprisonment" or "18 months" or "6 weeks" into months.
    Digits only. Word numbers ("two years") return null; Bedrock covers those. -#}
{% macro duration_to_months(col) -%}
case
    when {{ col }} is null then null
    when not regexp_like({{ col }}, '.*[0-9]+\\s*(years?|months?|weeks?).*', 'is') then null
    else
        coalesce(try_to_number(regexp_substr({{ col }}, '([0-9]+)\\s*years?',  1, 1, 'ie', 1)), 0) * 12
      + coalesce(try_to_number(regexp_substr({{ col }}, '([0-9]+)\\s*months?', 1, 1, 'ie', 1)), 0)
      + coalesce(try_to_number(regexp_substr({{ col }}, '([0-9]+)\\s*weeks?',  1, 1, 'ie', 1)), 0) * 0.25
end
{%- endmacro %}
