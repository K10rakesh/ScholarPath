# backend/schemas_member2.py
# Pydantic models for Member 2's portion: Citation Resolution, Verification, and Roadmap
# These models strictly follow the JSON contracts shared across the team

from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


# =============================================================================
# Enums - Standardized values across all Member 2 modules
# =============================================================================

class VerificationVerdict(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNRESOLVED = "unresolved"


class TrustStatus(str, Enum):
    TRUSTED = "trusted"
    CAUTION = "caution"
    LOW_TRUST = "low_trust"


class ClaimPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RoadmapNodeType(str, Enum):
    PREREQUISITE = "prerequisite"
    INTERMEDIATE = "intermediate"
    TARGET = "target"


class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"


class ProcessingStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


# =============================================================================
# Member 1 Output (imported for reference) - Contract 01
# =============================================================================

class Reference(BaseModel):
    ref_id: str = Field(..., description="Citation marker in '[N]' format")
    raw_text: str = Field(..., description="Full bibliography line")
    citation_style: str = "numbered"


class Section(BaseModel):
    section_id: str
    heading: str
    text: str


class Claim(BaseModel):
    claim_id: str
    claim_text: str
    citations: list[str]
    section: str
    section_id: str
    priority: str
    claim_type: str
    sentence_index: int


class ParsedPaper(BaseModel):
    """Contract 01 - Input from Member 1"""
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
    processing_status: str
    errors: list[dict] = []


# =============================================================================
# Member 2 Intermediate Output - Contract 02: Resolved Citations
# =============================================================================

class ResolvedCitation(BaseModel):
    """One resolved bibliography entry with real paper metadata"""
    ref_id: str
    resolution_status: ResolutionStatus
    matched_title: Optional[str] = None
    authors: list[str] = []
    year: Optional[int] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    paper_id: Optional[str] = None  # e.g. "arxiv_1409.0473"
    source_provider: Optional[str] = None  # "semantic_scholar", "arxiv"
    source_url: Optional[str] = None
    confidence: float = 0.0
    raw_text: str


class ResolvedCitationsOutput(BaseModel):
    """Contract 02 - 02_resolved_citations.json"""
    doc_id: str
    resolved_citations: list[ResolvedCitation]
    stats: dict
    processing_status: str = ProcessingStatus.SUCCESS
    errors: list[dict] = []


# =============================================================================
# Member 2 Final Output - Contract 03: Verification Report
# =============================================================================

class VerificationResult(BaseModel):
    """Verification result for one claim-citation pair"""
    verification_id: str
    claim_id: str
    claim_text: str
    ref_id: str
    citation_title: Optional[str] = None
    resolution_status: ResolutionStatus
    verdict: VerificationVerdict
    confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str
    evidence_span: Optional[str] = None
    used_text_source: str = "abstract"  # "abstract" or "full_text"


class TrustReport(BaseModel):
    """Aggregated trust assessment for the entire document"""
    trust_score: int = Field(..., ge=0, le=100)
    status: TrustStatus
    summary: str
    supported_count: int = 0
    partially_supported_count: int = 0
    unsupported_count: int = 0
    insufficient_evidence_count: int = 0
    unresolved_count: int = 0


class VerificationReportOutput(BaseModel):
    """Contract 03 - 03_verification_report.json"""
    doc_id: str
    verification_results: list[VerificationResult]
    trust_report: TrustReport
    stats: dict
    processing_status: str = ProcessingStatus.SUCCESS
    errors: list[dict] = []


# =============================================================================
# Member 3 Input Contract - Contract 04: Roadmap Request
# =============================================================================

class VerifiedClaimSummary(BaseModel):
    """Simplified claim info for roadmap generation"""
    claim_id: str
    claim_text: str
    verdict: VerificationVerdict
    confidence: float


class TrustReportSummary(BaseModel):
    """Simplified trust report for roadmap generation"""
    trust_score: int
    status: TrustStatus
    summary: str


class RoadmapConstraints(BaseModel):
    """Constraints for roadmap generation"""
    only_generate_if_trusted: bool = True
    max_nodes: int = 8


class RoadmapRequest(BaseModel):
    """Contract 04 - 04_roadmap_request.json - Input for Member 3"""
    doc_id: str
    title: str
    domain: str
    trust_report: TrustReportSummary
    verified_claims: list[VerifiedClaimSummary]
    target_topic: str
    key_concepts: list[str]
    constraints: RoadmapConstraints = RoadmapConstraints()


# =============================================================================
# Member 3 Output Contract - Contract 05: Roadmap Response
# =============================================================================

class RoadmapNode(BaseModel):
    """One node in the learning roadmap"""
    node_id: str
    label: str
    node_type: RoadmapNodeType
    level: int = Field(..., ge=1)
    description: str


class RoadmapEdge(BaseModel):
    """Dependency relationship between two nodes"""
    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")
    relation: str = "required_for"

    model_config = {"populate_by_name": True}


class ResourceSuggestion(BaseModel):
    """Suggested resource for a topic"""
    topic: str
    resource_type: str = "search_hint"
    value: str


class RoadmapResponseOutput(BaseModel):
    """Contract 05 - 05_roadmap_response.json"""
    doc_id: str
    target_topic: str
    roadmap_summary: str
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    reading_order: list[str]
    resource_suggestions: list[ResourceSuggestion] = []
    processing_status: str = ProcessingStatus.SUCCESS
    errors: list[dict] = []


# =============================================================================
# Combined Final Report - Contract 06: For Frontend
# =============================================================================

class ClaimsOverviewItem(BaseModel):
    """Simplified claim info for frontend display"""
    claim_id: str
    claim_text: str
    citations: list[str]
    verdict: VerificationVerdict
    confidence: float
    explanation: str


class RoadmapSummary(BaseModel):
    """Simplified roadmap for combined report"""
    target_topic: str
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    reading_order: list[str]


class PaperSummary(BaseModel):
    """Basic paper metadata for combined report"""
    title: str
    authors: list[str]
    domain: str


class FinalReportOutput(BaseModel):
    """Contract 06 - 06_final_report.json - Combined output for frontend"""
    doc_id: str
    paper: PaperSummary
    trust_report: TrustReport
    claims_overview: list[ClaimsOverviewItem]
    roadmap: RoadmapSummary
    processing_status: str = ProcessingStatus.SUCCESS
    errors: list[dict] = []
