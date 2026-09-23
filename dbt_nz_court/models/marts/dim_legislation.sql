select
    c.extraction_id,
    c.document_id,
    c.case_name,
    c.neutral_citation,
    c.court,
    c.judgment_date,

    legislation.value:act::string as act,
    legislation.value:section::string as section,
    legislation.value:evidence:page::number as source_page,
    legislation.value:evidence:text::string as evidence_text

from {{ ref('stg_case_extractions') }} c,
lateral flatten(input => c.legislation_cited) legislation
