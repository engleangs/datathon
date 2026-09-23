-- One row per charge section, e.g. "s 188(2) Crimes Act 1961".
select
    f.relative_path,
    f.neutral_citation,
    f.primary_offence_type,
    f.reform_period,
    trim(cs.value::string)                                                        as charge_section,
    regexp_substr(cs.value::string, '[A-Z][A-Za-z ()]+ Act [0-9]{4}')             as act
from {{ ref('fct_dc_decisions') }} f
join {{ ref('stg_dc_cortex') }} c using (relative_path),
     lateral flatten(input => c.charge_sections) cs
where nullif(trim(cs.value::string), '') is not null
