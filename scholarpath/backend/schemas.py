# =============================================================================
# backend/schemas.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   Defines the Pydantic data models for Contract 01 — the shared output
#   format produced by Member 1 (PDF Parser + Claim Extractor) and consumed
#   by Member 2 (Citation Resolver, Verification Agent).
#
#   THIS FILE IS THE TEAM'S SHARED CONTRACT.
#   Member 2 and Member 3 code AGAINST these types as their input spec.
#   Do NOT rename any field without coordinating with the whole team.
#
#   Also contains simplified schemas that Member 3 (Frontend) uses for
#   roadmap input and final report display (at the bottom of the file).
#
# CONNECTED TO:
#   ← backend/agents/pdf_parser.py        (creates ParsedPaper)
#   ← backend/agents/claim_extractor.py   (creates Claim objects)
#   ← backend/utils/citation_patterns.py  (creates Reference objects)
#   → backend/database.py                 (serialises/deserialises ParsedPaper)
#   → backend/main.py                     (type annotations on endpoints)
#   → backend/schemas_member2.py          (imports Reference, Section, Claim,
#                                           ParsedPaper as its own Contract 01 mirror)
# =============================================================================

from pydantic import BaseModel, model_validator, Field
from typing import Optional


# ── Contract 01 Models (Member 1 output) ─────────────────────────────────────

class Reference(BaseModel):
    """
    Represents one bibliography entry in the paper.
    e.g. "[3] Vaswani et al. Attention Is All You Need. NeurIPS 2017."

    ref_id MUST be in "[N]" format with square brackets — this is the key
    that links Claim.citations[] to resolved paper metadata in Member 2.
    """
    ref_id: str           # MUST be "[N]" format e.g. "[1]" (with brackets)
    raw_text: str         # full bibliography line as extracted from PDF
    citation_style: str = "numbered"  # only "numbered" is supported for MVP


class Section(BaseModel):
    """
    Represents one logical section of the paper (Introduction, Methods, etc.)
    Sections are detected heuristically by find_section_boundaries().

    section_id is a sequential string: "s1", "s2", "s3"...
    text contains the full raw text from this section's heading to the next.
    """
    section_id: str       # "s1", "s2", "s3" — ordered by appearance
    heading: str          # "Introduction", "Background", "Conclusion" etc.
    text: str             # full text content of this section


class Claim(BaseModel):
    """
    Represents one verifiable factual claim extracted from the paper.
    A claim is a sentence that:
      - makes a factual assertion (not opinion/speculation)
      - has at least one citation marker [N] to support it

    This is the primary unit of analysis for the verification pipeline.
    Member 2 verifies each Claim against its citations[] references.
    """
    claim_id: str         # "c1", "c2" — globally unique across the entire paper
    claim_text: str       # the exact sentence making the claim (no [idx:N] prefix)
    citations: list[str]  # ref_ids this claim cites e.g. ["[1]", "[3]"]
    section: str          # heading of the section this claim appears in
    section_id: str       # section_id of the section this claim appears in
    priority: str         # "high" | "medium" | "low" — importance of this claim
    claim_type: str       # "result" | "background" | "method" | "comparative"
    sentence_index: int   # position of this sentence in the full sentence list


class ParsedPaper(BaseModel):
    """
    CONTRACT 01 — The complete output of the PDF parsing + claim extraction pipeline.
    This is the single most important data structure in the entire system.

    When serialised to JSON, it becomes the backbone that every downstream
    pipeline stage (citation resolution, verification, roadmap generation) reads from.

    FIELD DESCRIPTIONS:
      doc_id          — the 8-char UUID assigned at upload time
      file_name       — original PDF filename (for display)
      title           — extracted paper title (heuristic)
      authors         — list of author names (heuristic, may be empty)
      source_type     — always "pdf_upload" for MVP (could be "arxiv_import" later)
      domain          — academic domain if detectable (None in most cases)
      abstract        — first ~1000 chars after "Abstract" heading
      full_text       — complete extracted text from all PDF pages
      sections        — list of Section objects (detected headings)
      references      — list of Reference objects (bibliography entries)
      claims          — list of Claim objects (LLM-extracted assertions)
      stats           — dict of counts: num_sections, num_references, num_claims, num_citation_sentences
      processing_status — "success" | "partial" | "failed"
      errors          — list of error dicts: {"code": str, "message": str}
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
    processing_status: str = "success"   # "success" | "partial" | "failed"
    errors: list[dict] = []

    def validate_citation_integrity(self) -> list[str]:
        """
        THE CRITICAL VALIDATION CHECK — run before returning ParsedPaper.

        Ensures every citation marker in claims[].citations exists in
        references[].ref_id. If this is broken, Member 2's citation resolver
        will silently fail to resolve those references.

        Returns empty list = all good.
        Returns list of violation strings = has dangling citations.

        WHY THIS MATTERS:
          The claim extractor (LLM) sometimes hallucinates citation markers
          like "[15]" that don't exist in the bibliography. If we let these
          through, citation_resolver will try to look up a non-existent ref_id,
          wasting API calls and producing misleading "unresolved" verdicts.
        """
        # Build a set of all known ref_ids for O(1) lookup
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


# =============================================================================
# Member 2 Schemas — used alongside schemas_member2.py
# These are simpler/older versions kept for backward compatibility
# The authoritative versions live in schemas_member2.py
# =============================================================================

class ResolvedCitation(BaseModel):
    """
    One bibliography entry matched to real paper metadata.
    resolution_status tells how well the match was found:
      "resolved"           → full metadata found (title, abstract, DOI)
      "partially_resolved" → found something but abstract missing
      "unresolved"         → no match found in any API
    """
    ref_id: str
    resolution_status: str      # "resolved" | "partially_resolved" | "unresolved"
    matched_title: Optional[str] = None
    authors: list[str] = []
    year: Optional[int] = None
    abstract: Optional[str] = None    # used as evidence for claim verification
    doi: Optional[str] = None
    paper_id: Optional[str] = None    # e.g. "semantic_1234abcd" or "arxiv_1706.03762"
    source_provider: Optional[str] = None  # "semantic_scholar" | "arxiv"
    source_url: Optional[str] = None
    confidence: Optional[float] = None    # 0-1 match confidence score
    raw_text: str                          # original bibliography line


class ResolvedCitationsReport(BaseModel):
    """Contract 02 wrapper — list of resolved citations with stats."""
    doc_id: str
    resolved_citations: list[ResolvedCitation]
    stats: dict
    processing_status: str = "success"
    errors: list[dict] = []


class VerificationResult(BaseModel):
    """
    Result of verifying one claim against one cited paper.
    verdict is the key field — used to colour-code claims green/yellow/red in UI.
    confidence_score (0-100) drives the Trust Score calculation.
    """
    verification_id: str
    claim_id: str
    claim_text: str
    ref_id: str
    citation_title: Optional[str] = None
    resolution_status: str
    verdict: str  # "supported" | "partially_supported" | "unsupported" | "insufficient_evidence" | "unresolved"
    confidence_score: float       # 0.0 to 100.0
    explanation: str              # human-readable reasoning from LLM
    evidence_span: Optional[str] = None     # quote from evidence that was key
    used_text_source: Optional[str] = None  # "abstract" | "fetched_content"

    @property
    def confidence(self) -> float:
        """
        Backward-compatible property returning confidence as 0-1 float.
        Internally we store 0-100 (confidence_score) but some older code
        expected 0-1. This property bridges both conventions.
        """
        return self.confidence_score / 100.0

    @model_validator(mode="before")
    @classmethod
    def _coerce_confidence_fields(cls, values):
        """
        Accepts either 'confidence' (0-1) or 'confidence_score' (0-100).
        Converts 'confidence' to 'confidence_score' if only the former is provided.
        Ensures backward compatibility with older code that used the 0-1 scale.
        """
        if isinstance(values, dict):
            if "confidence_score" not in values and "confidence" in values:
                values["confidence_score"] = float(values["confidence"]) * 100.0
        return values


class TrustReport(BaseModel):
    """
    Aggregated trust assessment for the entire document.
    trust_score (0-100) is the average confidence_score across all verified claims.
    status maps to a UI color: trusted=green, caution=yellow, low_trust=red.
    """
    trust_score: int           # 0-100 — average of all claim confidence scores
    status: str                # "trusted" | "caution" | "low_trust"
    summary: str               # human-readable summary sentence
    supported_count: Optional[int] = 0
    partially_supported_count: Optional[int] = 0
    unsupported_count: Optional[int] = 0
    insufficient_evidence_count: Optional[int] = 0
    unresolved_count: Optional[int] = 0


class VerificationReport(BaseModel):
    """Contract 03 wrapper — list of verification results + trust report."""
    doc_id: str
    verification_results: list[VerificationResult]
    trust_report: TrustReport
    stats: dict
    processing_status: str = "success"
    errors: list[dict] = []


# =============================================================================
# Member 3 Schemas — simplified types for roadmap and final report display
# =============================================================================

class VerifiedClaimSimple(BaseModel):
    """Simplified claim info passed to the roadmap generator."""
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
        """Convert legacy 0-1 confidence to 0-100 confidence_score."""
        if isinstance(values, dict):
            if "confidence_score" not in values and "confidence" in values:
                values["confidence_score"] = float(values["confidence"]) * 100.0
        return values


class RoadmapRequest(BaseModel):
    """
    Contract 04 — input payload for roadmap generation.
    Passed from verification agent to roadmap generator containing
    the trust summary and verified claims to build the learning path.
    """
    doc_id: str
    title: str
    domain: Optional[str] = None
    trust_report: TrustReport
    verified_claims: list[VerifiedClaimSimple]
    target_topic: str
    key_concepts: list[str]
    constraints: dict = {"only_generate_if_trusted": True, "max_nodes": 8}


class RoadmapNode(BaseModel):
    """
    One node in the learning roadmap graph.
    node_type controls visual styling in the frontend:
      "prerequisite"   → foundations to learn before the paper's topic
      "intermediate"   → concepts from the paper's key claims
      "target"         → the paper's main contribution / final goal
    level is used for vertical ordering in the flowchart (lower = learn first).
    """
    node_id: str
    label: str
    node_type: str       # "prerequisite" | "intermediate" | "target"
    level: int
    description: Optional[str] = None


class RoadmapEdge(BaseModel):
    """
    A directed dependency edge between two roadmap nodes.
    from_node → to_node means "must learn from_node before to_node".
    Uses Field(alias="from") because "from" is a reserved Python keyword.
    """
    from_node: str = Field(alias="from")    # source node_id
    to: str                                  # destination node_id
    relation: str = "required_for"           # always "required_for" in MVP


class ResourceSuggestion(BaseModel):
    """A search hint for finding learning resources on a topic."""
    topic: str
    resource_type: str   # always "search_hint" in MVP
    value: str           # e.g. "transformer attention mechanism tutorial beginner"


class RoadmapResponse(BaseModel):
    """Contract 05 — the full roadmap output from roadmap_generator.py."""
    doc_id: str
    target_topic: str
    roadmap_summary: str
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    reading_order: list[str]       # ordered list of topic labels (for simple display)
    resource_suggestions: list[ResourceSuggestion]
    processing_status: str = "success"
    errors: list[dict] = []


class ClaimOverview(BaseModel):
    """
    Simplified claim for the final report's claims_overview[] list.
    Combines fields from Claim + VerificationResult for frontend display.
    """
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
        """Convert legacy 0-1 confidence to 0-100 confidence_score."""
        if isinstance(values, dict):
            if "confidence_score" not in values and "confidence" in values:
                values["confidence_score"] = float(values["confidence"]) * 100.0
        return values


class PaperBrief(BaseModel):
    """Minimal paper metadata for the final report header."""
    title: str
    authors: list[str]
    domain: Optional[str] = None


class RoadmapBrief(BaseModel):
    """Minimal roadmap data for the final report (no resource suggestions)."""
    target_topic: str
    nodes: list[RoadmapNode]
    edges: list[RoadmapEdge]
    reading_order: list[str]


class FinalReport(BaseModel):
    """
    CONTRACT 06 — The combined final report consumed by the React frontend.
    Assembles data from all three pipeline stages into one response object.

    Frontend renders:
      paper         → paper title and authors in the result header
      trust_report  → the big trust score + status (green/yellow/red)
      claims_overview → expandable list of verified claims with verdicts
      roadmap          → the numbered learning path (reading_order)
    """
    doc_id: str
    paper: PaperBrief
    trust_report: TrustReport
    claims_overview: list[ClaimOverview]
    roadmap: RoadmapBrief
    processing_status: str = "success"
    errors: list[dict] = []
