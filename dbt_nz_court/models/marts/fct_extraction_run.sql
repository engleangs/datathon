-- One row per extraction attempt, including superseded ones.
-- Use this to compare models/prompts or track review rates over time.

select
    q.extraction_id,
    q.document_id,
    q.model_id,
    q.extraction_status,
    coalesce(q.agent_needs_human_review, false) as agent_needs_human_review,
    q.is_verified_for_default_analytics,
    q.evidence_verified,
    q.evidence_total,
    q.loaded_at as extracted_at,
    coalesce(q.extraction_id = latest.extraction_id, false) as is_latest

from {{ ref('int_case_quality') }} q
left join {{ ref('int_latest_extractions') }} latest
    on latest.document_id = q.document_id
