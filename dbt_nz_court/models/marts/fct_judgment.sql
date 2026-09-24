-- One row per judgment (source document), using its latest extraction.
-- Replaces fct_cases; filter on is_verified_for_default_analytics for the old fct_verified_cases.

select
    document_id as judgment_key,
    document_id,
    extraction_id,

    {{ name_key('court') }} as court_key,
    {{ name_key('case_category') }} as case_category_key,

    case_name,
    neutral_citation,
    judgment_date,
    outcome,

    extraction_status,
    coalesce(agent_needs_human_review, false) as agent_needs_human_review,
    is_verified_for_default_analytics,
    evidence_verified,
    evidence_total,

    model_id,
    loaded_at as extracted_at

from {{ ref('int_latest_extractions') }}
