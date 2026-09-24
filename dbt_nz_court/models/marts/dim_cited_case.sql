-- One row per cited case, keyed on its citation.
-- cited_judgment_key links to fct_judgment when the cited case is itself in the corpus,
-- which gives a judgment-to-judgment citation network.

with cited as (

    select
        cited_case_key,
        citation,
        cited_case_name
    from {{ ref('int_judgment_cases_cited') }}

),

corpus as (

    select
        {{ name_key('neutral_citation') }} as citation_key,
        min(document_id) as judgment_key
    from {{ ref('int_latest_extractions') }}
    where neutral_citation is not null
    group by 1

)

select
    cited.cited_case_key,
    min(cited.citation) as citation,
    mode(cited.cited_case_name) as cited_case_name,
    corpus.judgment_key as cited_judgment_key
from cited
left join corpus
    on corpus.citation_key = cited.cited_case_key
group by cited.cited_case_key, corpus.judgment_key
