-- One row per supporting passage the agent quoted for a judgment's metadata.
-- (Evidence for individual citations is on fct_legislation_citation / fct_case_citation.)

select
    {{ surrogate_key(['e.document_id', 'ev.index']) }} as evidence_key,
    e.document_id as judgment_key,
    ev.index as evidence_position,
    ev.value:page::number as evidence_page,
    ev.value:text::string as evidence_text
from {{ ref('int_latest_extractions') }} e,
    lateral flatten(input => e.source_evidence) ev
