-- One row per legislation reference in a judgment, with the section and supporting evidence.
-- Replaces the old dim_legislation (which was one row per reference, not per Act).

select
    legislation_citation_key,
    judgment_key,
    legislation_key,
    section,
    reference_position,
    evidence_page,
    evidence_text
from {{ ref('int_judgment_legislation') }}
