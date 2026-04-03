# backend/schemas.py
# These Pydantic models define the exact shape of our output contract.
# Member 2 codes against these shapes — do not rename any keys.

from pydantic import BaseModel, model_validator, Field
from typing import Optional


class Reference(BaseModel):
    # Represents one bibliography entry e.g. "[1] Vaswani et al. 2017..."
    ref_id: str           # MUST be in "[N]" format with brackets e.g. "[1]"
    raw_text: str         # full bibliography line as a string
    citation_style: str = "numbered"


class Section(BaseModel):
    # Represents one section of the paper e.g. Introduction, Methods
    section_id: str       # "s1", "s2", "s3" in order of appearance
    heading: str          # "Introduction", "Background" etc.
    text: str             # full text content of that section


class Claim(BaseModel):
    # Represents one verifiable factual claim extracted from the paper
    claim_id: str         # "c1", "c2" — globally unique across the paper
    claim_text: str       # the exact sentence making the claim
    citations: list[str]  # list of ref_ids this claim cites e.g. ["[1]", "[3]"]
    section: str          # heading of the section this claim is in
    section_id: str       # section_id of the section this claim is in
    priority: str         # "high" | "medium" | "low"
    claim_type: str       # "result" | "background" | "method" | "comparative"
    sentence_index: int   # position of this sentence in the full sentence list


class ParsedPaper(BaseModel):
    # This is the full Contract 01 — the output of our entire Phase 1+2 work.
    # When serialized to JSON, this becomes 01_parsed_paper.json
    doc_id: str
    file_name: str
    title: str
    authors: list[str]
    source_type: str = "pdf_upload"
    domain: Optional[str] = None
    abstract: Optional[str] = None
    full_text: str
    sections: list[Section]
    references: list[Reference]
    claims: list[Claim]
    stats: dict
    processing_status: str = "success"   # "success" | "partial" | "failed"
    errors: list[dict] = []

    def validate_citation_integrity(self) -> list[str]:
        """
        THE CRITICAL CHECK.
        Every citation marker inside claims[] must exist in references[].
        Member 2's citation resolver will silently fail if this is broken.
        Returns a list of violation strings (empty list = all good).
        """
        # Build a set of all known ref_ids from the references list
        known_ref_ids = {ref.ref_id for ref in self.references}
        violations = []

        for claim in self.claims:
            for cite in claim.citations:
                if cite not in known_ref_ids:
                    violations.append(
                        f"Claim '{claim.claim_id}' cites '{cite}' "
                        f"but no such ref_id exists in references[]"
                    )
        return violations


# --- Member 2 Schemas ---

class ResolvedCitation(BaseModel):
    ref_id: str
    resolution_status: str # "resolved" | "partially_resolved" | "unresolved"
    matched_title: Optional[str] = None
    authors: list[str] = []
    year: Optional[int] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    paper_id: Optional[str] = None
    source_provider: Optional[str] = None
    source_url: Optional[str] = None
    confidence: Optional[float] = None
    raw_text: str

class ResolvedCitationsReport(BaseModel):
    doc_id: str
    resolved_citations: list[ResolvedCitation]
    stats: dict
    processing_status: str = "success"
    errors: list[dict] = []

class VerificationResult(BaseModel):
    verification_id: str
    claim_id: str
    claim_text: str
    ref_id: str
    citation_title: Optional[str] = None
    resolution_status: str
    verdict: str  # "supported" | "partially_supported" | "unsupported" | "insufficient_evidence" | "unresolved"
    confidence_score: float  # Score from 0 to 100 based on comparison with abstract
    explanation: str
    evidence_span: Optional[str] = None
    used_text_source: Optional[str] = None

    @property
    def confidence(self) -> float:
        return self.confidence_score / 100.0

    @model_validator(mode="before")
    @classmethod
    def _coerce_confidence_fields(cls, values):
        if isinstance(values, dict):
            if "confidence_score" not in values and "confidence" in values:
                values["confidence_score"] = float(values["confidence"]) * 100.0
        return values

class TrustReport(BaseModel):
    trust_score: int
    status: str  # "trusted" | "caution" | "low_trust"
    summary: str
    supported_count: Optional[int] = 0
    partially_supported_count: Optional[int] = 0
    unsupported_count: Optional[int] = 0
    insufficient_evidence_count: Optional[int] = 0
    unresolved_count: Optional[int] = 0

class VerificationReport(BaseModel):
    doc_id: str
    verification_results: list[VerificationResult]
    trust_report: TrustReport
    stats: dict
    processing_status: str = "success"
    errors: list[dict] = []


# --- Member 3 Schemas ---

class VerifiedClaimSimple(BaseModel):
    claim_id: str
    claim_text: str
    verdict: str
    confidence_score: float

    @property
    def confidence(self) -> float:
        return self.confidence_score / 100.0

    @model_validator(mode="before")
    @classmethod
    def _coerce_confidence_fields(cls, values):
        if isinstance(values, dict):
            if "confidence_score" not in values and "confidence" in values:
                values["confidence_score"] = float(values["confidence"]) * 100.0
        return values

class RoadmapRequest(BaseModel):
    doc_id: str
    title: str
    domain: Optional[str] = None
    trust_report: TrustReport
    verified_claims: list[VerifiedClaimSimple]
    target_topic: str
    key_concepts: list[str]
    constraints: dict = {"only_generate_if_trusted": True, "max_nodes": 8}

class RoadmapNode(BaseModel):
    node_id: str
    label: str
    node_type: str # "prerequisite" | "intermediate" | "target"
    level: int
    description: Optional[str] = None

class RoadmapEdge(BaseModel):
    from_node: str = Field(alias="from")
    to: str
    relation: str = "required_for"
    
class ResourceSuggestion(BaseModel):
    topic: str
    resource_type: str # "search_hint"
    value: str

class RoadmapResponse(BaseModel):
    doc_id: str
    target_topic: str
    roadmap_summary: str
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    reading_order: list[str]
    resource_suggestions: list[ResourceSuggestion]
    processing_status: str = "success"
    errors: list[dict] = []

class ClaimOverview(BaseModel):
    claim_id: str
    claim_text: str
    citations: list[str]
    verdict: str
    confidence_score: float
    explanation: str

    @property
    def confidence(self) -> float:
        return self.confidence_score / 100.0

    @model_validator(mode="before")
    @classmethod
    def _coerce_confidence_fields(cls, values):
        if isinstance(values, dict):
            if "confidence_score" not in values and "confidence" in values:
                values["confidence_score"] = float(values["confidence"]) * 100.0
        return values

class PaperBrief(BaseModel):
    title: str
    authors: list[str]
    domain: Optional[str] = None

class RoadmapBrief(BaseModel):
    target_topic: str
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    reading_order: list[str]

class FinalReport(BaseModel):
    doc_id: str
    paper: PaperBrief
    trust_report: TrustReport
    claims_overview: list[ClaimOverview]
    roadmap: RoadmapBrief
    processing_status: str = "success"
    errors: list[dict] = []
