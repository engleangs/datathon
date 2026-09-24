-- One row per legal issue identified in a judgment.
-- Issues are free-text sentences specific to each judgment, so they are kept as
-- detail rows rather than a shared dimension.

with flattened as (

    select
        e.document_id as judgment_key,
        i.index as issue_position,
        {{ clean_text('i.value::string') }} as issue_text
    from {{ ref('int_latest_extractions') }} e,
        lateral flatten(input => e.legal_issues) i

)

select
    {{ surrogate_key(['judgment_key', 'issue_position']) }} as legal_issue_key,
    judgment_key,
    issue_position,
    issue_text
from flattened
where issue_text is not null
