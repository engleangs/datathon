-- One row per quality issue on a judgment's latest extraction, from four sources:
--   AGENT_UNCERTAINTY      fields the agent could not verify confidently
--   VALIDATION_REASON      why validation marked the extraction REVIEW_REQUIRED
--   MISSING_REFERENCE      references that could not be matched back to the PDF
--   PUBLICATION_MARKER     possible suppression / confidentiality markers

with src as (

    select
        document_id as judgment_key,
        uncertainties,
        validation:reasons as validation_reasons,
        missing_references,
        publication_restriction_markers
    from {{ ref('int_latest_extractions') }}

),

issues as (

    select judgment_key, 'AGENT_UNCERTAINTY' as issue_type, f.index as issue_position, f.value::string as issue_text
    from src, lateral flatten(input => src.uncertainties) f

    union all

    select judgment_key, 'VALIDATION_REASON', f.index, f.value::string
    from src, lateral flatten(input => src.validation_reasons) f

    union all

    select judgment_key, 'MISSING_REFERENCE', f.index, f.value::string
    from src, lateral flatten(input => src.missing_references) f

    union all

    select judgment_key, 'PUBLICATION_MARKER', f.index, f.value::string
    from src, lateral flatten(input => src.publication_restriction_markers) f

)

select
    {{ surrogate_key(['judgment_key', 'issue_type', 'issue_position']) }} as quality_issue_key,
    judgment_key,
    issue_type,
    issue_position,
    {{ clean_text('issue_text') }} as issue_text
from issues
