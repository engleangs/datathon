-- One row per judge named on a judgment.
-- The extraction stores judges as one string (e.g. "Winkelmann CJ, Glazebrook and O'Regan JJ"),
-- so it is split on commas, semicolons, "and" and "&", and common titles are stripped so that
-- "Smith J", "Justice Smith" and "Smith" resolve to the same judge.
-- This is a heuristic: review dim_judge periodically for names it has not handled.

with split as (

    select
        e.document_id as judgment_key,
        s.index as judge_position,
        trim(s.value::string) as raw_judge_name
    from {{ ref('int_latest_extractions') }} e,
        lateral split_to_table(
            regexp_replace(e.judge, '\\s+(and|&)\\s+|;', ',', 1, 0, 'i'),
            ','
        ) s
    where e.judge is not null

),

stripped as (

    select
        judgment_key,
        judge_position,
        regexp_replace(
            raw_judge_name,
            '^((the|hon\\.?|honourable|justice|judge|associate judge)\\s+)+|\\s+(jj|j|cj|p)\\.?$',
            '', 1, 0, 'i'
        ) as stripped_name
    from split

),

cleaned as (

    select
        judgment_key,
        judge_position,
        {{ clean_text('stripped_name') }} as judge_name
    from stripped

)

select
    judgment_key,
    {{ name_key('judge_name') }} as judge_key,
    judge_name,
    judge_position
from cleaned
where judge_name is not null
qualify row_number() over (
    partition by judgment_key, judge_key
    order by judge_position
) = 1
