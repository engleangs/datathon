-- One row per judge, after title stripping in int_judgment_judges.

select
    judge_key,
    min(judge_name) as judge_name
from {{ ref('int_judgment_judges') }}
group by 1
