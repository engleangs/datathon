-- One row per distinct legal topic on a judgment (flattened from legal_topics).

with flattened as (

    select
        e.document_id as judgment_key,
        t.index as topic_position,
        {{ clean_text('t.value::string') }} as topic_name
    from {{ ref('int_latest_extractions') }} e,
        lateral flatten(input => e.legal_topics) t

)

select
    judgment_key,
    {{ name_key('topic_name') }} as topic_key,
    topic_name,
    topic_position
from flattened
where topic_name is not null
qualify row_number() over (
    partition by judgment_key, topic_key
    order by topic_position
) = 1
