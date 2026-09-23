select
    registry,
    judgment_month,
    case_type,
    count(*)                                        as decisions,
    count_if(document_type = 'sentencing')          as sentencing_notes,
    median(days_hearing_to_judgment)                as median_days_to_judgment,
    avg(page_count)                                 as avg_pages
from {{ ref('fct_dc_decisions') }}
group by 1, 2, 3
