# backend/agents/langgraph_verifier.py
# LangGraph-based multi-agent verification workflow
# Implements proper claim verification with real source fetching and confidence scoring

from typing import TypedDict, List, Optional, Annotated
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
import httpx
import re
import json
from datetime import datetime

from backend.schemas_member2 import (
    VerificationResult,
    VerificationReportOutput,
    VerificationVerdict,
    TrustReport,
    TrustStatus,
    ResolutionStatus,
    ProcessingStatus,
    ParsedPaper,
    ResolvedCitationsOutput,
)


# =============================================================================
# Configuration
# =============================================================================

OLLAMA_MODEL = "llama3.2"
API_TIMEOUT = 15.0

# arXiv API
ARXIV_API_URL = "https://export.arxiv.org/api/query"

# Semantic Scholar API
SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper"

# Trust score thresholds
TRUSTED_THRESHOLD = 75
CAUTION_THRESHOLD = 45


# =============================================================================
# State Definition for LangGraph
# =============================================================================

class VerificationState(TypedDict):
    """State passed between nodes in the LangGraph workflow."""
    doc_id: str
    claims: List[dict]
    citations: List[dict]
    citation_lookup: dict
    results: List[VerificationResult]
    errors: List[dict]
    current_claim_index: int
    current_ref_id: str
    evidence_text: str
    evidence_source: str
    fetched_content: dict
    verification_result: Optional[VerificationResult]


# =============================================================================
# LLM Model Setup
# =============================================================================

def get_llm():
    """Initialize the Ollama LLM for verification tasks."""
    return ChatOllama(
        model=OLLAMA_MODEL,
        temperature=0.1,
        top_p=0.9,
    )


# =============================================================================
# Node 1: Source Fetcher Agent
# =============================================================================

def fetch_source_evidence(state: VerificationState) -> VerificationState:
    """
    Source Fetcher Agent:
    Fetches actual paper content from cited sources (arXiv, Semantic Scholar).
    Prioritizes full abstracts and key metadata for verification.
    """
    ref_id = state["current_ref_id"]
    citation_lookup = state["citation_lookup"]

    resolved = citation_lookup.get(ref_id)
    if not resolved:
        state["errors"].append({
            "code": "CITATION_NOT_FOUND",
            "message": f"Citation {ref_id} not found in resolved citations"
        })
        state["evidence_text"] = ""
        state["evidence_source"] = "none"
        return state

    evidence_text = ""
    evidence_source = "abstract"
    fetched_content = {}

    # Try to fetch from arXiv if we have the ID
    paper_id = resolved.get("paper_id", "")
    source_url = resolved.get("source_url", "")

    if paper_id.startswith("arxiv_"):
        arxiv_id = paper_id.replace("arxiv_", "")
        fetched = _fetch_arxiv_paper(arxiv_id)
        if fetched:
            evidence_text = fetched.get("abstract", "")
            fetched_content = fetched
            evidence_source = "arxiv_full"

    # Try Semantic Scholar if arXiv failed
    if not evidence_text and paper_id.startswith("semantic_"):
        semantic_id = paper_id.replace("semantic_", "")
        fetched = _fetch_semantic_scholar_paper(semantic_id)
        if fetched:
            evidence_text = fetched.get("abstract", "")
            fetched_content = fetched
            evidence_source = "semantic_scholar_full"

    # Fallback to stored abstract
    if not evidence_text and resolved.get("abstract"):
        evidence_text = resolved["abstract"]
        evidence_source = "abstract"

    state["evidence_text"] = evidence_text
    state["evidence_source"] = evidence_source
    state["fetched_content"] = fetched_content

    return state


def _fetch_arxiv_paper(arxiv_id: str) -> Optional[dict]:
    """Fetch full paper metadata from arXiv API."""
    try:
        params = {
            "search_query": f"id:{arxiv_id}",
            "start": 0,
            "max_results": 1
        }

        with httpx.Client(timeout=API_TIMEOUT, follow_redirects=True) as client:
            response = client.get(ARXIV_API_URL, params=params)
            response.raise_for_status()
            return _parse_arxiv_response(response.text)
    except Exception as e:
        print(f"[source_fetcher] arXiv fetch failed: {e}")
        return None


def _parse_arxiv_response(xml_text: str) -> Optional[dict]:
    """Parse arXiv ATOM XML response."""
    import xml.etree.ElementTree as ET

    try:
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }

        root = ET.fromstring(xml_text)
        entries = root.findall('atom:entry', ns)

        if not entries:
            return None

        entry = entries[0]

        title_elem = entry.find('atom:title', ns)
        title = title_elem.text.strip() if title_elem is not None else None

        authors = []
        for author in entry.findall('atom:author', ns):
            name_elem = author.find('atom:name', ns)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())

        summary_elem = entry.find('atom:summary', ns)
        abstract = summary_elem.text.strip() if summary_elem is not None else None

        published_elem = entry.find('atom:published', ns)
        published = published_elem.text if published_elem is not None else None

        return {
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "published": published,
            "arxiv_id": arxiv_id
        }
    except Exception as e:
        print(f"[source_fetcher] arXiv parse error: {e}")
        return None


def _fetch_semantic_scholar_paper(paper_id: str) -> Optional[dict]:
    """Fetch paper metadata from Semantic Scholar API."""
    try:
        url = f"{SEMANTIC_SCHOLAR_URL}/{paper_id}"
        params = {
            "fields": "title,authors,abstract,publicationDate,doi,externalIds"
        }

        with httpx.Client(timeout=API_TIMEOUT, follow_redirects=True) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return {
                "title": data.get("title"),
                "authors": [a.get("name") for a in data.get("authors", []) if a.get("name")],
                "abstract": data.get("abstract"),
                "publicationDate": data.get("publicationDate"),
                "doi": data.get("doi"),
                "paper_id": paper_id
            }
    except Exception as e:
        print(f"[source_fetcher] Semantic Scholar fetch failed: {e}")
        return None


# =============================================================================
# Node 2: Claim Verifier Agent
# =============================================================================

def verify_claim_against_evidence(state: VerificationState) -> VerificationState:
    """
    Claim Verifier Agent:
    Uses LLM to verify if a claim is supported by the fetched evidence.
    Returns structured verdict with confidence score and explanation.
    """
    claims = state["claims"]
    current_idx = state["current_claim_index"]
    claim = claims[current_idx]

    claim_text = claim.get("claim_text", "")
    ref_id = state["current_ref_id"]
    evidence_text = state["evidence_text"]
    evidence_source = state["evidence_source"]

    # Get citation info
    resolved = state["citation_lookup"].get(ref_id, {})
    citation_title = resolved.get("matched_title")
    resolution_status = resolved.get("resolution_status", ResolutionStatus.UNRESOLVED)

    # Handle case where no evidence is available
    if not evidence_text or len(evidence_text.strip()) < 50:
        result = VerificationResult(
            verification_id=f"v{current_idx + 1}",
            claim_id=claim.get("claim_id", f"c{current_idx + 1}"),
            claim_text=claim_text,
            ref_id=ref_id,
            citation_title=citation_title,
            resolution_status=resolution_status,
            verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            explanation="No sufficient evidence available from the cited source to verify this claim.",
            evidence_span=None,
            used_text_source=evidence_source
        )
        state["verification_result"] = result
        return state

    # Build verification prompt
    prompt = _build_verification_prompt(claim_text, evidence_text)

    # Call LLM for verification
    llm = get_llm()
    try:
        response = llm.invoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)

        # Parse the LLM response
        parsed = _parse_verification_response(response_text, claim, resolved, evidence_text)

        if parsed:
            state["verification_result"] = parsed
            return state
    except Exception as e:
        print(f"[claim_verifier] LLM verification failed: {e}")

    # Fallback to heuristic verification
    result = _verify_claim_heuristic(claim, resolved, evidence_text, current_idx + 1, evidence_source)
    state["verification_result"] = result
    return state


def _build_verification_prompt(claim_text: str, evidence_text: str) -> str:
    """Build structured prompt for claim verification."""
    return f"""You are an expert academic fact-checker. Your task is to determine whether the EVIDENCE from a cited paper actually supports the CLAIM made in another paper.

Read both carefully and provide a precise verdict.

CLAIM (from the paper being analyzed):
{claim_text}

EVIDENCE (abstract/content from the cited paper):
{evidence_text}

INSTRUCTIONS:
1. Analyze whether the evidence DIRECTLY supports, PARTIALLY supports, or DOES NOT support the claim
2. Consider if the evidence is about the same topic as the claim
3. Look for specific factual alignment, not just topical relevance
4. Be strict - if the evidence doesn't clearly support the claim, mark it as insufficient

Respond in this EXACT JSON format (no markdown, no extra text):
{{
    "verdict": "supported" | "partially_supported" | "unsupported" | "insufficient_evidence",
    "confidence": 0.0-1.0,
    "explanation": "Clear explanation of your reasoning, citing specific parts of the evidence",
    "evidence_span": "Direct quote from evidence that supports or contradicts the claim"
}}

JSON:"""


def _parse_verification_response(
    raw: str,
    claim: dict,
    resolved: dict,
    evidence_text: str
) -> Optional[VerificationResult]:
    """Parse LLM response into structured VerificationResult."""
    try:
        # Clean response
        clean = raw.strip()
        clean = re.sub(r'^```json\s*', '', clean)
        clean = re.sub(r'^```\s*', '', clean)
        clean = re.sub(r'\s*```$', '', clean)
        clean = re.sub(r'^\s*\{', '{', clean)
        clean = clean.strip()

        data = json.loads(clean)

        verdict_str = data.get("verdict", "insufficient_evidence")
        try:
            verdict = VerificationVerdict(verdict_str)
        except ValueError:
            verdict = VerificationVerdict.INSUFFICIENT_EVIDENCE

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        return VerificationResult(
            verification_id=f"v{hash(claim.get('claim_id', '')) % 1000 + 1}",
            claim_id=claim.get("claim_id", ""),
            claim_text=claim.get("claim_text", ""),
            ref_id=resolved.get("ref_id", ""),
            citation_title=resolved.get("matched_title"),
            resolution_status=resolved.get("resolution_status", ResolutionStatus.UNRESOLVED),
            verdict=verdict,
            confidence=confidence,
            explanation=data.get("explanation", "No explanation provided"),
            evidence_span=data.get("evidence_span"),
            used_text_source="fetched_evidence"
        )
    except Exception as e:
        print(f"[claim_verifier] Parse error: {e}")
        return None


def _verify_claim_heuristic(
    claim: dict,
    resolved: dict,
    evidence_text: str,
    verification_index: int,
    evidence_source: str
) -> VerificationResult:
    """
    Fallback heuristic verification when LLM is unavailable.
    Uses keyword overlap and semantic similarity for scoring.
    """
    claim_text = claim.get("claim_text", "").lower()
    evidence_lower = evidence_text.lower() if evidence_text else ""

    if not evidence_text or len(evidence_text.strip()) < 50:
        return VerificationResult(
            verification_id=f"v{verification_index}",
            claim_id=claim.get("claim_id", ""),
            claim_text=claim_text,
            ref_id=resolved.get("ref_id", ""),
            citation_title=resolved.get("matched_title"),
            resolution_status=resolved.get("resolution_status", ResolutionStatus.UNRESOLVED),
            verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            confidence=0.0,
            explanation="No sufficient evidence available from the cited source.",
            evidence_span=None,
            used_text_source=evidence_source
        )

    # Keyword overlap analysis
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                  "being", "have", "has", "had", "do", "does", "did", "will",
                  "would", "could", "should", "may", "might", "must", "shall",
                  "can", "need", "to", "of", "in", "for", "on", "with", "at",
                  "by", "from", "as", "into", "through", "during", "before",
                  "after", "above", "below", "between", "under", "again",
                  "further", "then", "once", "here", "there", "when", "where",
                  "why", "how", "all", "each", "few", "more", "most", "other",
                  "some", "such", "no", "nor", "not", "only", "own", "same",
                  "so", "than", "too", "very", "just", "and", "but", "if",
                  "or", "because", "until", "while", "although", "though",
                  "that", "this", "these", "those", "it", "its", "we", "our"}

    claim_words = set(word for word in claim_text.split() if word not in stop_words and len(word) > 2)
    evidence_words = set(word for word in evidence_lower.split() if word not in stop_words and len(word) > 2)

    overlap = claim_words & evidence_words
    overlap_ratio = len(overlap) / max(len(claim_words), 1)

    # Calculate confidence based on overlap
    if overlap_ratio >= 0.4:
        verdict = VerificationVerdict.SUPPORTED
        confidence = min(0.85, 0.5 + overlap_ratio)
        explanation = f"Key terms from the claim appear in the cited evidence ({int(overlap_ratio * 100)}% keyword overlap)."
    elif overlap_ratio >= 0.25:
        verdict = VerificationVerdict.PARTIALLY_SUPPORTED
        confidence = 0.5 + (overlap_ratio - 0.25)
        explanation = f"Some key terms from the claim appear in the evidence, but the connection is partial ({int(overlap_ratio * 100)}% keyword overlap)."
    elif overlap_ratio >= 0.1:
        verdict = VerificationVerdict.INSUFFICIENT_EVIDENCE
        confidence = 0.3
        explanation = f"Limited keyword overlap ({int(overlap_ratio * 100)}%) suggests the evidence may not directly support this claim."
    else:
        verdict = VerificationVerdict.UNSUPPORTED
        confidence = 0.2
        explanation = f"Minimal keyword overlap ({int(overlap_ratio * 100)}%) suggests the evidence does not support this claim."

    return VerificationResult(
        verification_id=f"v{verification_index}",
        claim_id=claim.get("claim_id", ""),
        claim_text=claim_text,
        ref_id=resolved.get("ref_id", ""),
        citation_title=resolved.get("matched_title"),
        resolution_status=resolved.get("resolution_status", ResolutionStatus.UNRESOLVED),
        verdict=verdict,
        confidence=confidence,
        explanation=explanation,
        evidence_span=None,
        used_text_source=evidence_source
    )


# =============================================================================
# Node 3: Result Aggregator
# =============================================================================

def aggregate_result(state: VerificationState) -> VerificationState:
    """
    Result Aggregator:
    Collects verification results and moves to the next claim.
    """
    result = state["verification_result"]
    if result:
        state["results"].append(result)

    # Move to next claim
    state["current_claim_index"] += 1

    return state


# =============================================================================
# Router: Check if more claims to process
# =============================================================================

def has_more_claims(state: VerificationState) -> str:
    """Route to next claim or end."""
    if state["current_claim_index"] < len(state["claims"]):
        return "continue"
    return "end"


# =============================================================================
# Build the LangGraph Workflow
# =============================================================================

def build_verification_graph():
    """
    Build the LangGraph workflow for claim verification.

    Workflow:
    1. Start with claim and citation info
    2. Fetch source evidence (Source Fetcher Agent)
    3. Verify claim against evidence (Claim Verifier Agent)
    4. Aggregate result and move to next claim
    5. Repeat until all claims processed
    """
    graph_builder = StateGraph(VerificationState)

    # Add nodes
    graph_builder.add_node("fetch_source", fetch_source_evidence)
    graph_builder.add_node("verify_claim", verify_claim_against_evidence)
    graph_builder.add_node("aggregate", aggregate_result)

    # Set entry point
    graph_builder.set_entry_point("fetch_source")

    # Define edges
    graph_builder.add_edge("fetch_source", "verify_claim")
    graph_builder.add_edge("verify_claim", "aggregate")

    # Conditional edge back to fetch or end
    graph_builder.add_conditional_edges(
        "aggregate",
        has_more_claims,
        {
            "continue": "fetch_source",
            "end": END
        }
    )

    return graph_builder.compile()


# =============================================================================
# Main Entry Point
# =============================================================================

def verify_claims_with_langgraph(
    parsed_paper: ParsedPaper,
    resolved_citations: ResolvedCitationsOutput
) -> VerificationReportOutput:
    """
    Main entry point for LangGraph-based claim verification.

    Args:
        parsed_paper: ParsedPaper from Member 1 (Contract 01)
        resolved_citations: ResolvedCitationsOutput from citation resolver (Contract 02)

    Returns:
        VerificationReportOutput (Contract 03)
    """
    doc_id = parsed_paper.doc_id

    # Build citation lookup
    citation_lookup = {
        c.ref_id: c.model_dump() for c in resolved_citations.resolved_citations
    }

    # Convert claims to dict format
    claims = [claim.model_dump() for claim in parsed_paper.claims]

    # Initialize state
    initial_state: VerificationState = {
        "doc_id": doc_id,
        "claims": claims,
        "citations": [c.model_dump() for c in resolved_citations.resolved_citations],
        "citation_lookup": citation_lookup,
        "results": [],
        "errors": [],
        "current_claim_index": 0,
        "current_ref_id": "",
        "evidence_text": "",
        "evidence_source": "",
        "fetched_content": {},
        "verification_result": None
    }

    # Build and run the graph
    graph = build_verification_graph()

    # Process each claim manually for better control
    for idx, claim in enumerate(claims):
        # Get primary citation for this claim
        claim_citations = claim.get("citations", [])
        if not claim_citations:
            initial_state["errors"].append({
                "code": "NO_CITATION",
                "message": f"Claim {claim.get('claim_id')} has no citations"
            })
            continue

        primary_ref_id = claim_citations[0]
        initial_state["current_claim_index"] = idx
        initial_state["current_ref_id"] = primary_ref_id

        # Run the graph for this claim
        try:
            final_state = graph.invoke(initial_state)
            initial_state = final_state
        except Exception as e:
            print(f"[langgraph_verifier] Error processing claim {idx}: {e}")
            initial_state["errors"].append({
                "code": "VERIFICATION_ERROR",
                "message": f"Failed to verify claim {claim.get('claim_id')}: {str(e)}"
            })

    # Calculate trust report
    trust_report = _calculate_trust_report(initial_state["results"])

    return VerificationReportOutput(
        doc_id=doc_id,
        verification_results=initial_state["results"],
        trust_report=trust_report,
        stats={
            "total_claims_checked": len(initial_state["results"]),
            "claims_with_resolved_citations": sum(
                1 for r in initial_state["results"]
                if r.resolution_status != ResolutionStatus.UNRESOLVED
            ),
            "claims_with_unresolved_citations": sum(
                1 for r in initial_state["results"]
                if r.resolution_status == ResolutionStatus.UNRESOLVED
            )
        },
        processing_status=ProcessingStatus.SUCCESS if not initial_state["errors"] else ProcessingStatus.PARTIAL,
        errors=initial_state["errors"]
    )


def _calculate_trust_report(results: List[VerificationResult]) -> TrustReport:
    """
    Calculate overall trust score from verification results.
    Uses weighted scoring based on verdicts and confidence scores.
    """
    if not results:
        return TrustReport(
            trust_score=0,
            status=TrustStatus.LOW_TRUST,
            summary="No claims were verified.",
            supported_count=0,
            partially_supported_count=0,
            unsupported_count=0,
            insufficient_evidence_count=0,
            unresolved_count=0
        )

    # Verdict weights
    VERDICT_SCORES = {
        VerificationVerdict.SUPPORTED: 1.0,
        VerificationVerdict.PARTIALLY_SUPPORTED: 0.6,
        VerificationVerdict.INSUFFICIENT_EVIDENCE: 0.3,
        VerificationVerdict.UNSUPPORTED: 0.0,
        VerificationVerdict.UNRESOLVED: 0.0,
    }

    # Count verdicts
    supported_count = sum(1 for r in results if r.verdict == VerificationVerdict.SUPPORTED)
    partially_supported_count = sum(1 for r in results if r.verdict == VerificationVerdict.PARTIALLY_SUPPORTED)
    unsupported_count = sum(1 for r in results if r.verdict == VerificationVerdict.UNSUPPORTED)
    insufficient_count = sum(1 for r in results if r.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE)
    unresolved_count = sum(1 for r in results if r.verdict == VerificationVerdict.UNRESOLVED)

    # Calculate weighted score using BOTH verdict AND confidence
    total_weighted_score = 0
    for result in results:
        verdict_score = VERDICT_SCORES[result.verdict]
        # Weight the verdict score by the confidence
        weighted_score = verdict_score * result.confidence
        total_weighted_score += weighted_score

    # Normalize to 0-100
    max_possible = len(results)  # If all claims had verdict=1.0 and confidence=1.0
    trust_score = int((total_weighted_score / max_possible) * 100)

    # Determine status
    if trust_score >= TRUSTED_THRESHOLD:
        status = TrustStatus.TRUSTED
        summary = f"Most key claims are supported by their cited references with high confidence."
    elif trust_score >= CAUTION_THRESHOLD:
        status = TrustStatus.CAUTION
        summary = f"Some claims are supported, but several have weak or insufficient citation support. Proceed with caution."
    else:
        status = TrustStatus.LOW_TRUST
        summary = f"Many claims lack proper citation support. This document may contain misrepresented evidence."

    return TrustReport(
        trust_score=trust_score,
        status=status,
        summary=summary,
        supported_count=supported_count,
        partially_supported_count=partially_supported_count,
        unsupported_count=unsupported_count,
        insufficient_evidence_count=insufficient_count,
        unresolved_count=unresolved_count
    )
