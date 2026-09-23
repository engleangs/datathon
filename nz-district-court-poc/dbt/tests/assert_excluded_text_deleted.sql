-- Governance test: excluded decisions must have no stored text.
select relative_path
from {{ source('raw', 'dc_docs') }}
where excluded_reason is not null
  and full_text is not null
