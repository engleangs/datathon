-- One row per legal topic.

select
    topic_key,
    min(topic_name) as topic_name
from {{ ref('int_judgment_topics') }}
group by 1
