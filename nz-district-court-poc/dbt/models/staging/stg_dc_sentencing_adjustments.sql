-- One row per uplift or discount the judge applied, in order.
select
    b.relative_path,
    a.index + 1                                      as step,
    a.value:factor::string                           as factor,
    lower(a.value:category::string)                  as category,
    lower(a.value:direction::string)                 as direction,
    try_to_double(a.value:percent::string)           as percent,
    try_to_double(a.value:months::string)            as months
from {{ ref('stg_dc_bedrock') }} b,
     lateral flatten(input => b.adjustments) a
