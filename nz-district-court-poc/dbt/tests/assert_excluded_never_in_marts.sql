-- Governance test: a Youth Court or Family Court decision must NEVER reach a mart.
-- Returns rows (= fails) if one does.
select f.relative_path, d.excluded_reason
from {{ ref('fct_dc_decisions') }} f
join {{ source('raw', 'dc_docs') }} d using (relative_path)
where d.excluded_reason is not null
   or f.neutral_citation ilike '%NZYC%'
   or f.neutral_citation ilike '%NZFC%'
