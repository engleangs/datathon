with extractions as (

    select *
    from {{ source('raw', 'case_extractions') }}

),

documents as (

    select *
    from {{ source('raw', 'documents') }}

)

select
    e.extraction_id,
    e.document_id,

    d.filename as source_document,
    d.source_url,
    d.sha256 as document_sha256,
    d.page_count,

    e.model_id,

    nullif(trim(e.extraction:case_name::string), '') as case_name,
    nullif(trim(e.extraction:neutral_citation::string), '') as neutral_citation,

    case
        when upper(trim(e.extraction:court::string)) in
            ('NZHC', 'HIGH COURT', 'HIGH COURT OF NEW ZEALAND')
            then 'HIGH COURT'

        when upper(trim(e.extraction:court::string)) in
            ('NZCA', 'COURT OF APPEAL', 'NEW ZEALAND COURT OF APPEAL')
            then 'COURT OF APPEAL'

        when upper(trim(e.extraction:court::string)) in
            ('NZSC', 'SUPREME COURT', 'SUPREME COURT OF NEW ZEALAND')
            then 'SUPREME COURT'

        else upper(trim(e.extraction:court::string))
    end as court,

    try_to_date(e.extraction:judgment_date::string) as judgment_date,
    nullif(trim(e.extraction:case_category::string), '') as case_category,

    e.extraction:legal_topics as legal_topics,
    e.extraction:legal_issues as legal_issues,
    e.extraction:legislation_cited as legislation_cited,
    e.extraction:cases_cited as cases_cited,

    nullif(trim(e.extraction:outcome::string), '') as outcome,
    nullif(trim(e.extraction:judge::string), '') as judge,

    e.extraction:source_evidence as source_evidence,
    e.extraction:uncertainties as uncertainties,
    e.extraction:needs_human_review::boolean as agent_needs_human_review,

    e.validation as validation,
    e.extraction_status,
    e.loaded_at

from extractions e
left join documents d
    on e.document_id = d.document_id
