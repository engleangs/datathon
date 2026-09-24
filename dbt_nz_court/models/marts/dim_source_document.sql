-- One row per ingested PDF. document_id is the SHA-256 of the file.

select
    document_id,
    source_document as filename,
    source_url,
    document_sha256,
    page_count
from {{ ref('int_latest_extractions') }}
