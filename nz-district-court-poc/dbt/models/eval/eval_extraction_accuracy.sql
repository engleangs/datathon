-- Field-level accuracy of the pipeline against hand-labelled gold data.
with gold as (select * from {{ ref('gold_labels') }}),
     pred as (select * from {{ ref('fct_dc_decisions') }}),

scored as (
    select
        g.relative_path,
        iff(upper(replace(p.neutral_citation, ' ', '')) = upper(replace(g.neutral_citation, ' ', '')), 1, 0) as citation_ok,
        iff(lower(p.registry) = lower(g.registry), 1, 0)                         as registry_ok,
        iff(p.judgment_date = g.judgment_date, 1, 0)                             as date_ok,
        iff(p.document_type = lower(g.document_type), 1, 0)                      as doctype_ok,
        iff(g.sentence_type is null, null,
            iff(p.sentence_type = lower(g.sentence_type), 1, 0))                 as sentence_type_ok,
        iff(g.end_sentence_months is null, null,
            iff(abs(p.end_sentence_months - g.end_sentence_months) <= 0.5, 1, 0)) as end_sentence_ok,
        iff(g.guilty_plea_percent is null, null,
            iff(abs(p.guilty_plea_percent - g.guilty_plea_percent) <= 1, 1, 0))  as plea_pct_ok
    from gold g
    left join pred p using (relative_path)
)

select 'neutral_citation' as field, avg(citation_ok) as accuracy, count(citation_ok) as n from scored
union all select 'registry',           avg(registry_ok),      count(registry_ok)      from scored
union all select 'judgment_date',      avg(date_ok),          count(date_ok)          from scored
union all select 'document_type',      avg(doctype_ok),       count(doctype_ok)       from scored
union all select 'sentence_type',      avg(sentence_type_ok), count(sentence_type_ok) from scored
union all select 'end_sentence_months (+/- 0.5)', avg(end_sentence_ok), count(end_sentence_ok) from scored
union all select 'guilty_plea_percent (+/- 1)',   avg(plea_pct_ok),     count(plea_pct_ok)     from scored
