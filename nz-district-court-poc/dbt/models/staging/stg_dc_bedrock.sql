select
    relative_path,
    lower(brief_raw:document_type::string)                 as document_type_bedrock,
    brief_raw:lead_offence::string                         as lead_offence,
    try_to_double(brief_raw:starting_point_months::string) as starting_point_months,
    try_to_double(brief_raw:guilty_plea_percent::string)   as guilty_plea_percent,
    try_to_double(brief_raw:personal_mitigation_percent::string)
                                                           as personal_mitigation_percent,
    try_to_double(brief_raw:end_sentence_months::string)   as end_sentence_months,
    lower(brief_raw:sentence_type::string)                 as sentence_type,
    try_to_boolean(brief_raw:home_detention_considered::string)
                                                           as home_detention_considered,
    try_to_double(brief_raw:reparation_nzd::string)        as reparation_nzd,
    brief_raw:outcome::string                              as outcome_bedrock,
    brief_raw:adjustments                                  as adjustments,
    try_to_double(brief_raw:confidence::string)            as confidence,
    brief_raw:_meta:model_id::string                       as model_id,
    brief_raw:_meta:input_tokens::number                   as input_tokens,
    brief_raw:_meta:output_tokens::number                  as output_tokens,
    brief_raw:error::string                                as bedrock_error,
    reason                                                 as routed_reason,
    processed_at
from {{ source('raw', 'dc_bedrock') }}
