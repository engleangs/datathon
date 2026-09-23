select
    *,
    coalesce(validation:evidence_verified::number, 0) as evidence_verified,
    coalesce(validation:evidence_total::number, 0) as evidence_total,
    validation:missing_references as missing_references,
    validation:publication_restriction_markers as publication_restriction_markers,

    case
        when extraction_status = 'ACCEPTED'
         and coalesce(agent_needs_human_review, false) = false
        then true
        else false
    end as is_verified_for_default_analytics

from {{ ref('stg_case_extractions') }}
