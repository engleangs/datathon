select
    c.extraction_id,
    c.document_id,
    c.case_name,
    c.neutral_citation,
    c.court,
    c.judgment_date,

    citation.value:citation::string as cited_case_citation,
    citation.value:case_name::string as cited_case_name,
    citation.value:evidence:page::number as source_page,
    citation.value:evidence:text::string as evidence_text

from {{ ref('stg_case_extractions') }} c,
lateral flatten(input => c.cases_cited) citation
