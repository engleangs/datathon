-- One row per court (names already standardised in stg_case_extractions).

select
    {{ name_key('court') }} as court_key,
    min({{ clean_text('court') }}) as court_name
from {{ ref('int_latest_extractions') }}
where {{ clean_text('court') }} is not null
group by 1
