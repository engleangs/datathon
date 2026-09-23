from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class EvidenceSnippet(BaseModel):
    page: Optional[int] = Field(
        default=None,
        description="1-based PDF page containing the supporting passage.",
    )
    text: Optional[str] = Field(
        default=None,
        description="Short passage copied from the judgment supporting the extracted fact.",
    )


class LegislationReference(BaseModel):
    act: str = Field(description="Name of the Act, regulation, or other legislation.")
    section: Optional[str] = Field(
        default=None,
        description="Section or provision if explicitly stated.",
    )
    evidence: Optional[EvidenceSnippet] = None


class CaseReference(BaseModel):
    citation: str = Field(description="Neutral or reported citation of the cited case.")
    case_name: Optional[str] = None
    evidence: Optional[EvidenceSnippet] = None


class CourtCaseExtraction(BaseModel):
    case_name: Optional[str] = None
    neutral_citation: Optional[str] = None
    court: Optional[str] = None
    judgment_date: Optional[date] = None
    case_category: Optional[str] = None

    legal_topics: list[str] = Field(default_factory=list)
    legal_issues: list[str] = Field(default_factory=list)

    legislation_cited: list[LegislationReference] = Field(default_factory=list)
    cases_cited: list[CaseReference] = Field(default_factory=list)

    outcome: Optional[str] = None
    judge: Optional[str] = None

    source_document: str = ""
    source_evidence: list[EvidenceSnippet] = Field(default_factory=list)

    publication_restriction_markers: list[str] = Field(default_factory=list)

    uncertainties: list[str] = Field(
        default_factory=list,
        description="Fields or conclusions the model could not verify confidently.",
    )
    needs_human_review: bool = False


class ValidationResult(BaseModel):
    status: str
    reasons: list[str] = Field(default_factory=list)
    missing_references: list[str] = Field(default_factory=list)
    verified_references: list[str] = Field(default_factory=list)
    evidence_verified: int = 0
    evidence_total: int = 0
    publication_restriction_markers: list[str] = Field(default_factory=list)
