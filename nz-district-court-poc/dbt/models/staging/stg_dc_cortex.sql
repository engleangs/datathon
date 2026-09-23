-- Flatten AI_EXTRACT output ({"response": {...}, "error": ...}) into typed columns.
with src as (select * from {{ source('raw', 'dc_cortex') }}),

f as (
    select
        relative_path,
        extract_raw:response as r,
        extract_raw:error::string as extract_error,
        offence_type_raw, civil_type_raw, summary, summary_model, processed_at
    from src
)

select
    relative_path,
    nullif(trim(r:case_name::string), '')                               as case_name,
    upper(regexp_substr(r:neutral_citation::string,
          '\\[[0-9]{4}\\]\\s*NZ[A-Za-z]+\\s*[0-9]+'))                     as neutral_citation,
    initcap(nullif(trim(r:registry::string), ''))                       as registry,
    upper(nullif(trim(r:file_number::string), ''))                      as file_number,
    case
        when upper(r:file_number::string) like 'CIV%' then 'civil'
        when upper(r:file_number::string) like 'CRI%' then 'criminal'
        when offence_type_raw is not null             then 'criminal'
        when civil_type_raw is not null               then 'civil'
        else 'unknown'
    end                                                                 as case_type,
    nullif(trim(r:judge::string), '')                                   as judge,
    try_to_date(r:judgment_date::string)                                as judgment_date,
    try_to_date(r:hearing_date::string)                                 as hearing_date,
    lower(nullif(trim(r:document_type::string), ''))                    as document_type_cortex,
    nullif(trim(r:prosecuting_agency::string), '')                      as prosecuting_agency,
    r:charges                                                           as charges,
    r:charge_sections                                                   as charge_sections,
    lower(nullif(trim(r:plea::string), ''))                             as plea,
    nullif(trim(r:starting_point::string), '')                          as starting_point_text,
    nullif(trim(r:end_sentence::string), '')                            as end_sentence_text,
    {{ duration_to_months("r:starting_point::string") }}                as starting_point_months_rule,
    {{ duration_to_months("r:end_sentence::string") }}                  as end_sentence_months_rule,
    nullif(trim(r:reparation::string), '')                              as reparation_text,
    try_to_number(replace(regexp_substr(r:reparation::string, '\\$\\s*([0-9,]+(\\.[0-9]{2})?)', 1, 1, 'e', 1), ',', ''), 12, 2)
                                                                        as reparation_nzd_rule,
    nullif(trim(r:civil_outcome::string), '')                           as civil_outcome,
    nullif(trim(r:publication_note::string), '')                        as publication_note,
    r:statutes_cited                                                    as statutes_cited,
    r:cases_cited                                                       as cases_cited,
    offence_type_raw:labels                                             as offence_types,
    offence_type_raw:labels[0]::string                                  as primary_offence_type,
    civil_type_raw:labels[0]::string                                    as civil_type,
    trim(summary)                                                       as summary,
    summary_model,
    extract_error,
    processed_at
from f
