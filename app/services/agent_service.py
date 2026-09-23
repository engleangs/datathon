from botocore.config import Config as BotocoreConfig
from strands import Agent
from strands.models import BedrockModel
from strands.types.exceptions import StructuredOutputException

from app.config import Settings
from app.schemas import CourtCaseExtraction
from app.services.court_tools import (
    get_page,
    scan_publication_restriction_markers,
    search_judgment,
    validate_reference,
)
from app.services.document_context import (
    reset_current_document,
    set_current_document,
)
from app.services.pdf_service import CourtDocument


SYSTEM_PROMPT = """
You are a document-extraction agent for publicly available New Zealand court judgments.

Your job is factual extraction and source grounding, not legal advice.

Rules:
1. Use only the currently loaded judgment as evidence.
2. Use the provided tools before making material claims.
3. Start by inspecting page 1 and searching for case metadata.
4. For every extracted legislation name and case citation, use validate_reference.
5. Preserve page numbers and short supporting passages where possible.
6. Never invent a missing value. Use null/empty values and explain uncertainty.
7. Never attempt to identify anonymised or suppressed people.
8. Run scan_publication_restriction_markers before finishing.
9. If publication/suppression/confidentiality markers appear, set needs_human_review=true.
10. Clearly distinguish the court's decision/outcome from arguments made by a party.
"""


def _build_agent(settings: Settings) -> Agent:
    settings.require_bedrock()

    boto_config = BotocoreConfig(
        retries={"max_attempts": 3, "mode": "standard"},
        connect_timeout=10,
        read_timeout=180,
    )

    model = BedrockModel(
        model_id=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=0.0,
        max_tokens=4096,
        boto_client_config=boto_config,
    )

    return Agent(
        model=model,
        tools=[
            search_judgment,
            get_page,
            validate_reference,
            scan_publication_restriction_markers,
        ],
        system_prompt=SYSTEM_PROMPT,
    )


def analyse_judgment(
    document: CourtDocument,
    user_request: str,
    settings: Settings,
) -> CourtCaseExtraction:
    token = set_current_document(document)

    try:
        agent = _build_agent(settings)

        prompt = f"""
A judgment named "{document.filename}" is loaded and contains {document.page_count} pages.

User request:
{user_request}

Perform a grounded extraction. Use tools to inspect and validate the judgment.
Return the result using the required structured output schema.
"""

        result = agent(
            prompt,
            structured_output_model=CourtCaseExtraction,
        )

        extraction = result.structured_output
        if extraction is None:
            raise RuntimeError("The agent returned no structured output.")

        extraction.source_document = document.filename
        return extraction

    except StructuredOutputException as exc:
        raise RuntimeError(f"Structured output validation failed: {exc}") from exc
    finally:
        reset_current_document(token)
