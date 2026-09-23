-- Headline PoC question: did discounts change after the Sentencing (Reform)
-- Amendment Act 2025 came into force (29 June 2025)?
-- A small hand-picked sample shows the METHOD works. It is not evidence about the law.
select
    reform_period,
    coalesce(primary_offence_type, 'all')                            as offence_type,
    count(*)                                                         as sentencing_decisions,
    avg(guilty_plea_percent)                                         as avg_guilty_plea_pct,
    avg(personal_mitigation_percent)                                 as avg_personal_mitigation_pct,
    max(personal_mitigation_percent)                                 as max_personal_mitigation_pct,
    count_if(over_mitigation_cap)                                    as decisions_over_40pct,
    avg(div0(end_sentence_months, nullif(starting_point_months, 0))) as avg_end_to_start_ratio,
    count_if(sentence_type = 'home detention')                       as home_detention,
    count_if(sentence_type = 'imprisonment')                         as imprisonment,
    count_if(has_s27_discount)                                       as with_s27_discount,
    count_if(needs_review)                                           as needs_review
from {{ ref('fct_dc_decisions') }}
where case_type = 'criminal'
  and document_type = 'sentencing'
group by grouping sets ((reform_period), (reform_period, primary_offence_type))
