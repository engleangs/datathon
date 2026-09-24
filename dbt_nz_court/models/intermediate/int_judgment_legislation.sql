-- One row per legislation reference on a judgment (flattened from legislation_cited).
-- The same Act can appear more than once (e.g. different sections), so rows are
-- keyed on their position in the list rather than de-duplicated.

with flattened as (

    select
        e.document_id as judgment_key,
        l.index as reference_position,
        {{ clean_text('l.value:act::string') }} as act_name,
        {{ clean_text('l.value:section::string') }} as section,
        l.value:evidence:page::number as evidence_page,
        l.value:evidence:text::string as evidence_text
    from {{ ref('int_latest_extractions') }} e,
        lateral flatten(input => e.legislation_cited) l

)

select
    {{ surrogate_key(['judgment_key', 'reference_position']) }} as legislation_citation_key,
    judgment_key,
    {{ name_key('act_name') }} as legislation_key,
    act_name,
    section,
    reference_position,
    evidence_page,
    evidence_text
from flattened
where act_name is not null
