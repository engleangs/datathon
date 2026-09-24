-- One row per piece of legislation (Act or regulation). Sections live on fct_legislation_citation.

select
    legislation_key,
    min(act_name) as act_name
from {{ ref('int_judgment_legislation') }}
group by 1
