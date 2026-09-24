import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import uuid

import snowflake.connector

from app.config import Settings
from app.schemas import CourtCaseExtraction, ValidationResult
from app.services.pdf_service import CourtDocument


def _require_https_origin(value: str, setting_name: str) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.netloc
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
    ):
        raise RuntimeError(f"{setting_name} must be an HTTPS origin.")
    return value.rstrip("/")


def generate_streamlit_embed_url(settings: Settings) -> str:
    """Mint a single-use URL for the configured Streamlit in Snowflake app."""
    settings.require_snowflake_embed()

    account_url = _require_https_origin(
        settings.snowflake_account_url,
        "SNOWFLAKE_ACCOUNT_URL",
    )
    parent_origin = _require_https_origin(settings.parent_origin, "PARENT_ORIGIN")

    database = quote(settings.streamlit_database, safe="")
    schema = quote(settings.streamlit_schema, safe="")
    app = quote(settings.streamlit_app, safe="")
    endpoint = (
        f"{account_url}/api/v2/databases/{database}/schemas/{schema}/"
        f"streamlits/{app}:generate-embed-url"
    )
    request = Request(
        endpoint,
        data=json.dumps({"parent_origin": parent_origin}).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.snowflake_embed_pat}",
            "X-Snowflake-Authorization-Token-Type": "PROGRAMMATIC_ACCESS_TOKEN",
            "X-Snowflake-Role": settings.snowflake_embed_role,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(
            f"Snowflake embed URL request failed (HTTP {exc.code}): {detail}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Snowflake embed URL request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Snowflake embed URL response was not valid JSON.") from exc

    if not isinstance(response_data, dict):
        raise RuntimeError("Snowflake embed URL response was not a JSON object.")

    embed_url = response_data.get("embed_url")
    if not isinstance(embed_url, str) or not embed_url:
        raise RuntimeError("Snowflake embed URL response did not contain embed_url.")

    embed_url_parts = urlsplit(embed_url)
    if embed_url_parts.scheme != "https" or not embed_url_parts.netloc:
        raise RuntimeError("Snowflake returned an invalid embed URL.")

    return embed_url

class DuplicateDocumentError(Exception):
    """This document has already been submitted into the CourtLens system."""

def document_exists(sha256: str, settings: Settings) -> bool:
    conn = _connection(settings)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM CASE_EXTRACTIONS ce
            JOIN DOCUMENTS d ON d.DOCUMENT_ID = ce.DOCUMENT_ID
            WHERE d.SHA256 = %s
            LIMIT 1
            """,
            (sha256,),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()

def _connection(settings: Settings):
    settings.require_snowflake()

    kwargs = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "password": settings.snowflake_password,
        "warehouse": settings.snowflake_warehouse,
        "database": settings.snowflake_database,
        "schema": settings.snowflake_schema,
    }

    if settings.snowflake_role:
        kwargs["role"] = settings.snowflake_role

    return snowflake.connector.connect(**kwargs)


def save_extraction(
    document: CourtDocument,
    extraction: CourtCaseExtraction,
    validation: ValidationResult,
    settings: Settings,
) -> str:
    extraction_id = str(uuid.uuid4())

    extraction_json = json.dumps(
        extraction.model_dump(mode="json"),
        ensure_ascii=False,
    )
    validation_json = json.dumps(
        validation.model_dump(mode="json"),
        ensure_ascii=False,
    )

    conn = _connection(settings)

    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            MERGE INTO DOCUMENTS AS target
            USING (
                SELECT
                    %s AS DOCUMENT_ID,
                    %s AS SHA256,
                    %s AS FILENAME,
                    %s AS SOURCE_URL,
                    %s AS PAGE_COUNT
            ) AS source
            ON target.DOCUMENT_ID = source.DOCUMENT_ID
            WHEN NOT MATCHED THEN
                INSERT (
                    DOCUMENT_ID,
                    SHA256,
                    FILENAME,
                    SOURCE_URL,
                    PAGE_COUNT,
                    INGESTED_AT
                )
                VALUES (
                    source.DOCUMENT_ID,
                    source.SHA256,
                    source.FILENAME,
                    source.SOURCE_URL,
                    source.PAGE_COUNT,
                    CURRENT_TIMESTAMP()
                )
            """,
            (
                document.document_id,
                document.sha256,
                document.filename,
                document.source_url,
                document.page_count,
            ),
        )

        cursor.execute(
            """
            INSERT INTO CASE_EXTRACTIONS (
                EXTRACTION_ID, DOCUMENT_ID, MODEL_ID,
                EXTRACTION, VALIDATION, EXTRACTION_STATUS, LOADED_AT
            )
            SELECT %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s), %s, CURRENT_TIMESTAMP()
            WHERE NOT EXISTS (
                SELECT 1
                FROM CASE_EXTRACTIONS ce
                JOIN DOCUMENTS d ON d.DOCUMENT_ID = ce.DOCUMENT_ID
                WHERE d.SHA256 = %s
            )
            """,
            (
                extraction_id,
                document.document_id,
                settings.bedrock_model_id,
                extraction_json,
                validation_json,
                validation.status,
                document.sha256,
            ),
        )

        if cursor.rowcount == 0:
            raise DuplicateDocumentError(
                f"{document.filename} (SHA-256 {document.sha256[:12]}…) has already been saved."
            )

        conn.commit()
        return extraction_id

    finally:
        conn.close()
