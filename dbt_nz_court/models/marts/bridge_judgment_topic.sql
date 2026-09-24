-- Many-to-many between judgments and legal topics.

select
    {{ surrogate_key(['judgment_key', 'topic_key']) }} as judgment_topic_key,
    judgment_key,
    topic_key,
    topic_position
from {{ ref('int_judgment_topics') }}
