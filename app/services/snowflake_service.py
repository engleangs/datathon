import json
import uuid

import snowflake.connector

from app.config import Settings
from app.schemas import CourtCaseExtraction, ValidationResult
from app.services.pdf_service import CourtDocument

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
