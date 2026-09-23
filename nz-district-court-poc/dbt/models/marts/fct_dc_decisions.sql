{{ config(
    post_hook = "alter table {{ this }} modify column case_name set masking policy {{ target.database }}.OPS.MASK_PARTY_NAME"
) }}
-- One row per INCLUDED District Court decision. Excluded decisions (Youth / Family Court)
-- never reach this table. case_name is masked for every role except the pipeline role.

with docs as (select * from {{ ref('stg_dc_docs') }} where not is_excluded),
     cx   as (select * from {{ ref('stg_dc_cortex') }}),
     br   as (select * from {{ ref('stg_dc_bedrock') }}),

adj as (
    select
        relative_path,
        count(*)                                                                  as adjustment_count,
        sum(iff(direction = 'uplift',   months, 0))                               as uplift_months,
        sum(iff(direction = 'discount', months, 0))                               as discount_months,
        count_if(months is null)                                                  as adjustments_without_months,
        boolor_agg(category = 'cultural_background_s27')                          as has_s27_discount,
        boolor_agg(category = 'youth')                                            as has_youth_discount,
        boolor_agg(category = 'remorse')                                          as has_remorse_discount
    from {{ ref('stg_dc_sentencing_adjustments') }}
    group by 1
),

joined as (
    select
        d.relative_path,
        d.file_name,
        d.page_count,
        cx.case_name,
        coalesce(cx.neutral_citation, upper(d.citation_found))                   as neutral_citation,
        cx.registry,
        cx.file_number,
        cx.case_type,
        cx.judge,
        cx.judgment_date,
        date_trunc('month', cx.judgment_date)                                     as judgment_month,
        cx.hearing_date,
        datediff('day', cx.hearing_date, cx.judgment_date)                        as days_hearing_to_judgment,
        coalesce(br.document_type_bedrock, cx.document_type_cortex)               as document_type,
        cx.prosecuting_agency,
        cx.plea,
        array_size(cx.charges)                                                    as charge_count,
        cx.primary_offence_type,
        cx.offence_types,
        cx.civil_type,
        br.lead_offence,

        -- Sentencing: Bedrock numbers first, digit-only rule parse as fallback
        coalesce(br.starting_point_months, cx.starting_point_months_rule)         as starting_point_months,
        coalesce(br.end_sentence_months,   cx.end_sentence_months_rule)           as end_sentence_months,
        br.sentence_type,
        br.guilty_plea_percent,
        br.personal_mitigation_percent,
        br.home_detention_considered,
        coalesce(br.reparation_nzd, cx.reparation_nzd_rule)                       as reparation_nzd,
        cx.starting_point_text,
        cx.end_sentence_text,

        adj.adjustment_count,
        adj.uplift_months,
        adj.discount_months,
        adj.has_s27_discount,
        adj.has_youth_discount,
        adj.has_remorse_discount,

        -- Arithmetic check: start + uplifts - discounts should land near the end sentence.
        iff(adj.adjustments_without_months = 0
              and br.starting_point_months is not null
              and br.end_sentence_months is not null,
            round(br.starting_point_months + adj.uplift_months - adj.discount_months
                  - br.end_sentence_months, 1),
            null)                                                                 as arithmetic_gap_months,

        -- Cross-check: two independent reads of the end sentence should agree.
        iff(br.end_sentence_months is not null and cx.end_sentence_months_rule is not null,
            abs(br.end_sentence_months - cx.end_sentence_months_rule) <= 0.5, null) as end_sentence_agrees,

        cx.civil_outcome,
        cx.publication_note,
        cx.publication_note is not null                                           as has_publication_note,
        array_size(cx.statutes_cited)                                             as statutes_cited_count,
        array_size(cx.cases_cited)                                                as cases_cited_count,
        cx.summary,
        br.outcome_bedrock,
        br.confidence                                                             as bedrock_confidence,
        br.relative_path is not null                                              as has_bedrock_analysis,
        cx.extract_error,
        br.bedrock_error
    from docs d
    left join cx  on cx.relative_path  = d.relative_path
    left join br  on br.relative_path  = d.relative_path
    left join adj on adj.relative_path = d.relative_path
)

select
    *,
    case when judgment_date is null then 'unknown'
         when judgment_date >= '{{ var("sentencing_reform_date") }}'::date then 'after reform'
         else 'before reform' end                                                 as reform_period,
    personal_mitigation_percent > {{ var('personal_mitigation_cap_pct') }}        as over_mitigation_cap,
    (neutral_citation is null
     or judgment_date is null
     or extract_error is not null
     or bedrock_error is not null
     or coalesce(bedrock_confidence, 1) < {{ var('min_bedrock_confidence') }}
     or abs(coalesce(arithmetic_gap_months, 0)) > 1
     or end_sentence_agrees = false)                                               as needs_review
from joined
