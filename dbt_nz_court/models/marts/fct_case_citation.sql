-- One row per case cited in a judgment, with supporting evidence.
-- Replaces fct_case_citations. Join dim_cited_case for the cited case's name
-- and, where it is in the corpus, its own judgment.

select
    case_citation_key,
    judgment_key,
    cited_case_key,
    reference_position,
    evidence_page,
    evidence_text
from {{ ref('int_judgment_cases_cited') }}
