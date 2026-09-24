from pathlib import Path
import re

from app.schemas import CourtCaseExtraction
from app.services.pdf_service import CourtDocument


DEFAULT_DEBUG_DIRECTORY = Path(".debug/extractions")


def save_debug_extraction(
    extraction: CourtCaseExtraction,
    document: CourtDocument,
    output_directory: Path = DEFAULT_DEBUG_DIRECTORY,
) -> Path:
    """Save a structured extraction as local JSON for debugging."""
    output_directory.mkdir(parents=True, exist_ok=True)

    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(document.filename).stem).strip("-")
    safe_stem = safe_stem or "judgment"
    output_path = output_directory / f"{safe_stem}-{document.sha256[:12]}.json"
    output_path.write_text(
        extraction.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
