-- One row per case citation on a judgment (flattened from cases_cited).

with flattened as (

    select
        e.document_id as judgment_key,
        c.index as reference_position,
        {{ clean_text('c.value:citation::string') }} as citation,
        {{ clean_text('c.value:case_name::string') }} as cited_case_name,
        c.value:evidence:page::number as evidence_page,
        c.value:evidence:text::string as evidence_text
    from {{ ref('int_latest_extractions') }} e,
        lateral flatten(input => e.cases_cited) c

)

select
    {{ surrogate_key(['judgment_key', 'reference_position']) }} as case_citation_key,
    judgment_key,
    {{ name_key('citation') }} as cited_case_key,
    citation,
    cited_case_name,
    reference_position,
    evidence_page,
    evidence_text
from flattened
where citation is not null
