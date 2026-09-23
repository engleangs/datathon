-- The "sentencing ladder": every uplift and discount, with the decision's context.
select
    a.relative_path,
    f.neutral_citation,
    f.registry,
    f.judgment_date,
    f.reform_period,
    f.primary_offence_type,
    f.starting_point_months,
    a.step,
    a.factor,
    a.category,
    a.direction,
    a.percent,
    a.months
from {{ ref('stg_dc_sentencing_adjustments') }} a
join {{ ref('fct_dc_decisions') }} f using (relative_path)
