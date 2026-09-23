select *
from {{ ref('fct_cases') }}
where is_verified_for_default_analytics = true
