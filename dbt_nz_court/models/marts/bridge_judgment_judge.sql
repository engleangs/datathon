-- Many-to-many between judgments and judges (allows multi-judge panels).

select
    {{ surrogate_key(['judgment_key', 'judge_key']) }} as judgment_judge_key,
    judgment_key,
    judge_key,
    judge_position
from {{ ref('int_judgment_judges') }}
