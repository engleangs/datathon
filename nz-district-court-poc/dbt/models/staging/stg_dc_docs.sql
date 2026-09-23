select
    relative_path,
    split_part(relative_path, '/', -1)       as file_name,
    file_size_bytes,
    page_count,
    citation_found,
    excluded_reason,
    excluded_reason is not null              as is_excluded,
    length(full_text)                        as text_chars,
    parse_error is not null                  as has_parse_error,
    parsed_at
from {{ source('raw', 'dc_docs') }}
