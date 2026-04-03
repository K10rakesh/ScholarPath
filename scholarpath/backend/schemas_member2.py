# =============================================================================
# backend/schemas_member2.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   The AUTHORITATIVE Pydantic models for Member 2's pipeline stages.
#   Defines Contracts 02 through 06 — the exact JSON shapes for:
#     Contract 02 → ResolvedCitationsOutput   (citation resolution output)
#     Contract 03 → VerificationReportOutput  (LLM claim verification output)
#     Contract 04 → RoadmapRequest            (roadmap generator input spec)
#     Contract 05 → RoadmapResponseOutput     (roadmap generator output)
#     Contract 06 → FinalReportOutput         (combined report for frontend)
#
#   Uses Python Enums for all categorical fields (verdict, trust status, etc.)
#   to prevent typos and enable IDE auto-complete across the team.
#
#   MIRROR OF schemas.py:
#     Member 2 needs its own copy of Member 1's types (Reference, Section,
#     Claim, ParsedPaper) to avoid circular imports. The definitions here
#     are structurally identical to schemas.py but live in this file.
#
# CONNECTED TO:
#   ← backend/agents/citation_resolver.py    (uses ResolvedCitation, ResolvedCitationsOutput)
#   ← backend/agents/verification_agent.py   (uses VerificationResult, TrustReport, VerificationReportOutput)
#   ← backend/agents/langgraph_verification.py (uses VerificationResult, VerificationVerdict)
#   ← backend/agents/roadmap_generator.py    (uses RoadmapNode, RoadmapEdge, RoadmapResponseOutput)
#   ← backend/main.py                         (assembles FinalReportOutput)
# =============================================================================

from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
from enum import Enum


# =============================================================================
# Enums — Standardized categorical values used across all Member 2 modules
# Using Enum (not plain strings) prevents typos and enables IDE validation
# =============================================================================

class VerificationVerdict(str, Enum):
    """
    The possible outcomes when verifying a claim against its cited evidence.
    str Enum means these serialize naturally to/from JSON strings.
    """
    SUPPORTED = "supported"                    # evidence directly confirms the claim
    PARTIALLY_SUPPORTED = "partially_supported"  # evidence related but incomplete
    UNSUPPORTED = "unsupported"                # evidence contradicts or is irrelevant
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # abstract too short to judge
    UNRESOLVED = "unresolved"                  # citation couldn't be matched to a paper


class TrustStatus(str, Enum):
    """
    Overall document trust level derived from the average confidence score.
    Maps to UI colors: TRUSTED=green, CAUTION=yellow, LOW_TRUST=red.
    Thresholds: TRUSTED ≥ 75, CAUTION 45-74, LOW_TRUST < 45
    """
    TRUSTED = "trusted"
    CAUTION = "caution"
    LOW_TRUST = "low_trust"


class ClaimPriority(str, Enum):
    """Priority of a claim — set by the LLM during claim extraction."""
    HIGH = "high"      # core result/contribution claim
    MEDIUM = "medium"  # supporting evidence
    LOW = "low"        # peripheral background claim


class RoadmapNodeType(str, Enum):
    """
    Type of a node in the learning roadmap.
    Controls visual styling in the frontend:
      PREREQUISITE → learn first (left/top)
      INTERMEDIATE → middle concepts
      TARGET       → the paper's main topic (final node)
    """
    PREREQUISITE = "prerequisite"
    INTERMEDIATE = "intermediate"
    TARGET = "target"


class ResolutionStatus(str, Enum):
    """How well a bibliography entry was matched to a real paper."""
    RESOLVED = "resolved"                    # full metadata found
    PARTIALLY_RESOLVED = "partially_resolved"  # found but incomplete
    UNRESOLVED = "unresolved"                # no match found


class ProcessingStatus(str, Enum):
    """Status of any pipeline stage output."""
    SUCCESS = "success"
    PARTIAL = "partial"   # completed with some errors
    FAILED = "failed"


# =============================================================================
# Member 1 Output Mirror — Contract 01 (imported as input to Member 2)
# These are structurally identical to schemas.py but kept here to avoid
# circular imports between schemas.py and agent files.
# =============================================================================

class Reference(BaseModel):
    """One bibliography entry. ref_id must be '[N]' format."""
    ref_id: str = Field(..., description="Citation marker in '[N]' format")
    raw_text: str = Field(..., description="Full bibliography line")
    citation_style: str = "numbered"


class Section(BaseModel):
    """One detected section of the paper (Introduction, Methods, etc.)."""
    section_id: str
    heading: str
    text: str


class Claim(BaseModel):
    """One verifiable factual claim extracted from the paper by the LLM."""
    claim_id: str
    claim_text: str
    citations: list[str]     # list of ref_ids that back this claim
    section: str
    section_id: str
    priority: str
    claim_type: str
    sentence_index: int


class ParsedPaper(BaseModel):
    """
    Contract 01 — Full output from Member 1's PDF parsing pipeline.
    This is the primary INPUT to all Member 2 agents.
    """
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
# Contract 02 — Resolved Citations Output
# Output of citation_resolver.py — each reference matched to real metadata
# =============================================================================

class ResolvedCitation(BaseModel):
    """
    One bibliography entry matched to real paper metadata from Semantic Scholar/arXiv.

    ref_id links back to the original Reference in ParsedPaper.references.
    abstract is the most critical field — it's used as evidence text
    in the LangGraph verification workflow.

    confidence (0-1) reflects how well the API result matched the citation text.
    """
    ref_id: str                              # links to Reference.ref_id e.g. "[3]"
    resolution_status: ResolutionStatus      # how well the match was found
    matched_title: Optional[str] = None      # actual paper title from API
    authors: list[str] = []
    year: Optional[int] = None
    abstract: Optional[str] = None           # KEY FIELD — used as verification evidence
    doi: Optional[str] = None
    paper_id: Optional[str] = None           # e.g. "semantic_1234abcd" or "arxiv_1706.03762"
    source_provider: Optional[str] = None    # "semantic_scholar" | "arxiv"
    source_url: Optional[str] = None
    confidence: float = 0.0                  # 0-1 match confidence
    raw_text: str                            # original bibliography line (for debugging)


class ResolvedCitationsOutput(BaseModel):
    """
    Contract 02 — Full output of citation_resolver.py.
    Contains one ResolvedCitation per Reference in the ParsedPaper.
    stats tracks how many references were successfully resolved.
    """
    doc_id: str
    resolved_citations: list[ResolvedCitation]
    stats: dict     # {"total_references": N, "resolved_count": M, "unresolved_count": K}
    processing_status: str = ProcessingStatus.SUCCESS
    errors: list[dict] = []


# =============================================================================
# Contract 03 — Verification Report Output
# Output of verification_agent.py — claim verdicts + overall trust score
# =============================================================================

class VerificationResult(BaseModel):
    """
    Verification result for one claim-citation pair.
    The LangGraph workflow produces one of these per claim.

    verdict + confidence_score are the two key fields:
      - verdict drives the UI color (green/yellow/red)
      - confidence_score accumulates into the document trust score

    evidence_span is an optional quote from the cited paper's abstract
    that the LLM identified as the key evidence passage.
    """
    verification_id: str
    claim_id: str
    claim_text: str
    ref_id: str
    citation_title: Optional[str] = None
    resolution_status: ResolutionStatus
    verdict: VerificationVerdict
    confidence_score: float = Field(..., ge=0.0, le=100.0)  # always 0-100
    explanation: str                         # LLM's reasoning in plain English
    evidence_span: Optional[str] = None      # quoted supporting/contradicting evidence
    used_text_source: str = "abstract"       # "abstract" | "fetched_content"

    @property
    def confidence(self) -> float:
        """
        Backward-compatible 0-1 confidence for any code using the old scale.
        confidence_score is canonical (0-100); this property converts on the fly.
        """
        return self.confidence_score / 100.0

    @model_validator(mode="before")
    @classmethod
    def _coerce_confidence_fields(cls, values):
        """
        Auto-converts 'confidence' (0-1) → 'confidence_score' (0-100)
        if only the old-style field is provided. Ensures backward compat
        when deserializing older cached JSON.
        """
        if isinstance(values, dict):
            if "confidence_score" not in values and "confidence" in values:
                values["confidence_score"] = float(values["confidence"]) * 100.0
        return values


class TrustReport(BaseModel):
    """
    Overall trust assessment for the entire document.

    trust_score (0-100) = average of all VerificationResult.confidence_scores.
    status maps the score to a categorical level:
      ≥ 75  → TRUSTED   (green: roadmap uses LLM)
      45-74 → CAUTION   (yellow: roadmap uses LLM with warnings)
      < 45  → LOW_TRUST (red: roadmap uses heuristics only)

    The count fields give a breakdown of how many claims fell in each verdict bucket.
    """
    trust_score: int = Field(..., ge=0, le=100)
    status: TrustStatus
    summary: str                     # human-readable one-sentence assessment
    supported_count: int = 0
    partially_supported_count: int = 0
    unsupported_count: int = 0
    insufficient_evidence_count: int = 0
    unresolved_count: int = 0


class VerificationReportOutput(BaseModel):
    """
    Contract 03 — Full verification report from verification_agent.py.
    Contains one VerificationResult per claim + the aggregate TrustReport.
    This is the key artifact that activates or blocks the Trust Gate.
    """
    doc_id: str
    verification_results: list[VerificationResult]
    trust_report: TrustReport
    stats: dict   # {"total_claims_checked": N, "claims_with_resolved_citations": M, ...}
    processing_status: str = ProcessingStatus.SUCCESS
    errors: list[dict] = []


# =============================================================================
# Contract 04 — Roadmap Request (Member 3 Input Spec)
# What the verification stage sends to the roadmap generator as its input
# =============================================================================

class VerifiedClaimSummary(BaseModel):
    """Simplified claim info for roadmap generation — strips heavy fields."""
    claim_id: str
    claim_text: str
    verdict: VerificationVerdict
    confidence_score: float = Field(..., ge=0.0, le=100.0)

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


class TrustReportSummary(BaseModel):
    """Simplified trust report for roadmap generator input."""
    trust_score: int
    status: TrustStatus
    summary: str


class RoadmapConstraints(BaseModel):
    """
    Configuration constraints passed to the roadmap generator.
    only_generate_if_trusted: if True, skip LLM and use heuristic when LOW_TRUST.
    max_nodes: cap the roadmap at this many nodes to keep it readable.
    """
    only_generate_if_trusted: bool = True
    max_nodes: int = 8


class RoadmapRequest(BaseModel):
    """
    Contract 04 — Input specification for the roadmap generator.
    Contains a subset of the verification output needed to build the learning path.
    """
    doc_id: str
    title: str
    domain: str
    trust_report: TrustReportSummary
    verified_claims: list[VerifiedClaimSummary]
    target_topic: str
    key_concepts: list[str]
    constraints: RoadmapConstraints = RoadmapConstraints()


# =============================================================================
# Contract 05 — Roadmap Response Output
# Output of roadmap_generator.py — a directed graph of learning concepts
# =============================================================================

class RoadmapNode(BaseModel):
    """
    One concept node in the learning roadmap graph.
    node_type controls visual styling:
      prerequisite → foundational knowledge needed before the paper
      intermediate → concepts from the paper's key verified claims
      target       → the paper's main topic (the goal of the roadmap)
    level determines vertical order in the flowchart (1 = learn first).
    """
    node_id: str
    label: str
    node_type: RoadmapNodeType
    level: int = Field(..., ge=1)    # must be ≥ 1
    description: str                 # why this node appears in the roadmap


class RoadmapEdge(BaseModel):
    """
    A directed dependency edge: from_node must be learned before to_node.
    Uses Field(alias="from") because "from" is a Python reserved keyword.
    populate_by_name=True allows both "from" and "from_node" in input dicts.
    """
    from_node: str = Field(..., alias="from")   # source node_id
    to_node: str = Field(..., alias="to")        # target node_id
    relation: str = "required_for"               # always "required_for" in MVP

    model_config = {"populate_by_name": True}


class ResourceSuggestion(BaseModel):
    """
    A learning resource suggestion for one roadmap topic.
    resource_type="search_hint" means the value is a search query string,
    not a direct URL. Keeps the system from having to maintain curated URLs.
    """
    topic: str
    resource_type: str = "search_hint"   # "search_hint" in MVP
    value: str                           # e.g. "transformer neural network tutorial"


class FlowchartNode(BaseModel):
    """
    Extension of RoadmapNode with (x, y) position data for visual rendering.
    x_position and y_position are percentages (0-100) for flexible layout.
    Generated by _generate_flowchart() in roadmap_generator.py.
    """
    node_id: str
    label: str
    node_type: RoadmapNodeType
    level: int
    description: str
    x_position: float = 0.0   # 0-100% horizontal position
    y_position: float = 0.0   # 0-100% vertical position (0=top, 100=bottom)


class FlowchartData(BaseModel):
    """
    Complete visual layout data for rendering the roadmap as a flowchart.
    nodes have position data; edges are the same as the roadmap edges.
    layout_type="vertical" means the graph flows top-to-bottom.
    """
    nodes: list[FlowchartNode]
    edges: list[RoadmapEdge]
    layout_type: str = "vertical"               # "vertical" | "horizontal" | "tree"
    flowchart_summary: str = "Learning path flowchart"


class RoadmapResponseOutput(BaseModel):
    """
    Contract 05 — Full roadmap output from roadmap_generator.py.

    nodes + edges form the learning dependency graph.
    reading_order is a flat ordered list for simple sequential display.
    flowchart contains pre-computed position data for visual rendering.
    """
    doc_id: str
    target_topic: str
    roadmap_summary: str                      # one-sentence description of the path
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    reading_order: list[str]                  # node labels in study order
    resource_suggestions: list[ResourceSuggestion] = []
    flowchart: FlowchartData = None           # optional: visual positioning data
    processing_status: str = ProcessingStatus.SUCCESS
    errors: list[dict] = []


# =============================================================================
# Contract 06 — Final Report (Combined output for React frontend)
# Assembled in main.py from all three pipeline stage outputs
# =============================================================================

class ClaimsOverviewItem(BaseModel):
    """
    Simplified claim entry in the final report's claims list.
    Merges fields from Claim (text, citations) and VerificationResult (verdict, explanation).
    This is exactly what the frontend's ExpandableClaim component renders.
    """
    claim_id: str
    claim_text: str
    citations: list[str]         # list of ref_ids this claim cites
    verdict: VerificationVerdict # determines the colored dot in the UI
    confidence_score: float = Field(..., ge=0.0, le=100.0)
    explanation: str             # LLM's plain English reasoning

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


class RoadmapSummary(BaseModel):
    """
    Simplified roadmap for the final report — omits resource_suggestions
    and raw LLM data. Only what the frontend needs to render the learning path.
    """
    target_topic: str
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    reading_order: list[str]
    flowchart: FlowchartData = None   # optional visualization data


class PaperSummary(BaseModel):
    """Basic paper metadata for the final report header display."""
    title: str
    authors: list[str]
    domain: str


class FinalReportOutput(BaseModel):
    """
    Contract 06 — The combined final report consumed by the React frontend.
    This is the JSON returned by POST /full-pipeline and GET /final-report.

    Frontend renders:
      paper           → header: title + authors
      trust_report    → big trust score (color = hsl mapped to score)
      claims_overview → expandable claim cards (green/yellow/red dots)
      roadmap         → numbered reading order list + flowchart
    """
    doc_id: str
    paper: PaperSummary
    trust_report: TrustReport
    claims_overview: list[ClaimsOverviewItem]
    roadmap: RoadmapSummary
    processing_status: str = ProcessingStatus.SUCCESS
    errors: list[dict] = []
