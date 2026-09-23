select
    extraction_id,
    document_id,
    source_document,
    source_url,
    document_sha256,
    page_count,

    case_name,
    neutral_citation,
    court,
    judgment_date,
    case_category,

    legal_topics,
    legal_issues,
    outcome,
    judge,

    extraction_status,
    is_verified_for_default_analytics,

    evidence_verified,
    evidence_total,
    missing_references,
    publication_restriction_markers,

    model_id,
    loaded_at

from {{ ref('int_case_quality') }}
