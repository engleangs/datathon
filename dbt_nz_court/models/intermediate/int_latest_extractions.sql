-- One row per source document: its most recent extraction.
-- A document can be re-extracted (e.g. after a prompt or model change), so all
-- judgment-level models build from this to avoid double counting.
-- Every extraction is still available in fct_extraction_run.

select *
from {{ ref('int_case_quality') }}
qualify row_number() over (
    partition by document_id
    order by loaded_at desc, extraction_id desc
) = 1
