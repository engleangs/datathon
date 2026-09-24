-- One row per case category. Categories differing only by case or spacing share a row.

select
    {{ name_key('case_category') }} as case_category_key,
    min({{ clean_text('case_category') }}) as case_category_name
from {{ ref('int_latest_extractions') }}
where {{ clean_text('case_category') }} is not null
group by 1
