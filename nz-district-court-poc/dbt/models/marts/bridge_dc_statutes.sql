-- One row per (decision, Act cited). Which Acts come up most in the District Court?
select
    f.relative_path,
    f.neutral_citation,
    f.case_type,
    f.reform_period,
    initcap(trim(regexp_replace(regexp_replace(s.value::string, '^(the|The)\\s+', ''),
                                '\\s*\\(NZ\\)\\s*$', '')))                        as statute,
    try_to_number(regexp_substr(s.value::string, '(18|19|20)[0-9]{2}'))           as statute_year
from {{ ref('fct_dc_decisions') }} f
join {{ ref('stg_dc_cortex') }} c using (relative_path),
     lateral flatten(input => c.statutes_cited) s
where nullif(trim(s.value::string), '') is not null
