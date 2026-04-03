# backend/agents/langgraph_verification.py
# LangGraph-based multi-agent verification workflow
# Uses specialized agents for source fetching, claim verification, and trust calculation

import re
import json
import httpx
import xml.etree.ElementTree as ET
from typing import TypedDict, List, Optional, Annotated, Literal
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langgraph.graph import StateGraph, END

from backend.schemas_member2 import (
    VerificationResult,
    VerificationVerdict,
    ResolutionStatus,
    TrustReport,
    TrustStatus,
    ParsedPaper,
    ResolvedCitationsOutput,
    ResolvedCitation,
)


# =============================================================================
# Configuration
# =============================================================================

OLLAMA_MODEL = "llama3.2"
VERDICT_SCORES = {
    VerificationVerdict.SUPPORTED: 1.0,
    VerificationVerdict.PARTIALLY_SUPPORTED: 0.6,
    VerificationVerdict.INSUFFICIENT_EVIDENCE: 0.3,
    VerificationVerdict.UNSUPPORTED: 0.0,
    VerificationVerdict.UNRESOLVED: 0.0,
}
TRUSTED_THRESHOLD = 75
CAUTION_THRESHOLD = 45


# =============================================================================
# State Definition - Shared state passed between nodes
# =============================================================================

class VerificationState(TypedDict):
    """State passed between LangGraph nodes"""
    claim_id: str
    claim_text: str
    resolved_citation: ResolvedCitation
    paper_full_text: Optional[str]
    fetched_evidence: str
    verification_result: Optional[dict]
    confidence_score: float
    error: Optional[str]


# =============================================================================
# Agent 1: Source Fetcher - Fetches real paper content
# =============================================================================

class SourceFetcher:
    """Fetches actual paper content from academic sources"""

    ARXIV_API = "https://export.arxiv.org/api/query"
    SEMANTIC_SCHOLAR_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
    SEMANTIC_SCHOLAR_PAPER = "https://api.semanticscholar.org/graph/v1/paper"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch(self, state: VerificationState) -> VerificationState:
        """Fetch evidence from the cited source"""
        citation = state["resolved_citation"]

        # Priority 1: Try Semantic Scholar if we have paper_id
        if citation.paper_id and citation.paper_id.startswith("semantic_"):
            paper_id = citation.paper_id.replace("semantic_", "")
            evidence = self._fetch_semantic_scholar_paper(paper_id)
            if evidence:
                state["fetched_evidence"] = evidence
                return state

        # Priority 2: Try arXiv if we have arxiv_id
        if citation.paper_id and citation.paper_id.startswith("arxiv_"):
            arxiv_id = citation.paper_id.replace("arxiv_", "")
            evidence = self._fetch_arxiv_paper(arxiv_id)
            if evidence:
                state["fetched_evidence"] = evidence
                return state

        # Priority 3: Search by title if we have a matched title
        if citation.matched_title:
            # Try Semantic Scholar search first
            evidence = self._search_semantic_scholar(citation.matched_title)
            if evidence:
                state["fetched_evidence"] = evidence
                return state

            # Fall back to arXiv search
            evidence = self._search_arxiv(citation.matched_title)
            if evidence:
                state["fetched_evidence"] = evidence
                return state

        # Priority 4: Use abstract as fallback
        state["fetched_evidence"] = citation.abstract or ""
        return state

    def _fetch_semantic_scholar_paper(self, paper_id: str) -> Optional[str]:
        """Fetch full paper details from Semantic Scholar"""
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(
                    f"{self.SEMANTIC_SCHOLAR_PAPER}/{paper_id}",
                    params={
                        "fields": "title,abstract,authors,publicationDate,journal,referenceCount"
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    return self._format_semantic_scholar_result(data)
        except Exception as e:
            print(f"[SourceFetcher] Semantic Scholar fetch error: {e}")
        return None

    def _fetch_arxiv_paper(self, arxiv_id: str) -> Optional[str]:
        """Fetch paper from arXiv API"""
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(
                    self.ARXIV_API,
                    params={
                        "search_query": f"id:{arxiv_id}",
                        "start": 0,
                        "max_results": 1
                    }
                )
                if response.status_code == 200:
                    result = self._parse_arxiv_response(response.text)
                    return result
        except Exception as e:
            print(f"[SourceFetcher] arXiv fetch error: {e}")
        return None

    def _search_semantic_scholar(self, title: str) -> Optional[str]:
        """Search Semantic Scholar by title"""
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(
                    self.SEMANTIC_SCHOLAR_SEARCH,
                    params={
                        "query": title[:200],
                        "limit": 1,
                        "fields": "title,abstract,authors,publicationDate,journal"
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("data"):
                        return self._format_semantic_scholar_result(data["data"][0])
        except Exception as e:
            print(f"[SourceFetcher] Semantic Scholar search error: {e}")
        return None

    def _search_arxiv(self, title: str) -> Optional[str]:
        """Search arXiv by title"""
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                response = client.get(
                    self.ARXIV_API,
                    params={
                        "search_query": f"ti:{title}",
                        "start": 0,
                        "max_results": 1
                    }
                )
                if response.status_code == 200:
                    result = self._parse_arxiv_response(response.text)
                    return result
        except Exception as e:
            print(f"[SourceFetcher] arXiv search error: {e}")
        return None

    def _format_semantic_scholar_result(self, data: dict) -> str:
        """Format Semantic Scholar result as evidence text"""
        parts = []
        if data.get("title"):
            parts.append(f"Title: {data['title']}")
        if data.get("abstract"):
            parts.append(f"Abstract: {data['abstract']}")
        if data.get("authors"):
            authors = ", ".join([a.get("name", "") for a in data["authors"] if a.get("name")])
            if authors:
                parts.append(f"Authors: {authors}")
        if data.get("publicationDate"):
            parts.append(f"Published: {data['publicationDate']}")
        if data.get("journal"):
            journal = data["journal"]
            if isinstance(journal, dict) and journal.get("name"):
                parts.append(f"Journal: {journal['name']}")
        return "\n".join(parts)

    def _parse_arxiv_response(self, xml_text: str) -> Optional[str]:
        """Parse arXiv ATOM XML response"""
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
            parts = []

            # Title
            title_elem = entry.find('atom:title', ns)
            if title_elem is not None and title_elem.text:
                parts.append(f"Title: {title_elem.text.strip()}")

            # Authors
            authors = []
            for author in entry.findall('atom:author', ns):
                name_elem = author.find('atom:name', ns)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text.strip())
            if authors:
                parts.append(f"Authors: {', '.join(authors)}")

            # Summary
            summary_elem = entry.find('atom:summary', ns)
            if summary_elem is not None and summary_elem.text:
                parts.append(f"Abstract: {summary_elem.text.strip()}")

            # Published
            published_elem = entry.find('atom:published', ns)
            if published_elem is not None and published_elem.text:
                parts.append(f"Published: {published_elem.text}")

            return "\n".join(parts) if parts else None

        except Exception as e:
            print(f"[SourceFetcher] arXiv XML parse error: {e}")
            return None


# =============================================================================
# Agent 2: Claim Verifier - Uses LLM to verify claim against evidence
# =============================================================================

class ClaimVerifier:
    """Verifies if a claim is supported by the fetched evidence"""

    def __init__(self):
        self.llm = ChatOllama(model=OLLAMA_MODEL, temperature=0.1)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert academic fact-checker. Your task is to determine whether
            EVIDENCE from a cited paper actually SUPPORTS a CLAIM made in another paper.

            Be strict and precise. A claim is only SUPPORTED if the evidence directly confirms it.
            A claim is PARTIALLY_SUPPORTED if the evidence is related but doesn't fully prove it.
            A claim is UNSUPPORTED if the evidence contradicts it or is irrelevant.

            Always respond with valid JSON only, no markdown or explanations."""),
            ("human", """CLAIM: {claim_text}

EVIDENCE from cited paper:
{evidence_text}

Determine if the evidence supports the claim. Consider:
1. Does the evidence directly confirm the claim's main assertion?
2. Are the key concepts and findings aligned?
3. Is there any contradiction?

Respond in this exact JSON format:
{{
    "verdict": "supported" | "partially_supported" | "unsupported" | "insufficient_evidence",
    "confidence": 0.0-1.0,
    "explanation": "Brief explanation of your reasoning",
    "evidence_span": "Quote the specific evidence that supports or contradicts"
}}""")
        ])
        self.parser = JsonOutputParser()

    def verify(self, state: VerificationState) -> VerificationState:
        """Verify claim against fetched evidence"""
        claim_text = state["claim_text"]
        evidence = state["fetched_evidence"]

        # Check if we have any evidence
        if not evidence or len(evidence.strip()) < 20:
            state["verification_result"] = {
                "verdict": "insufficient_evidence",
                "confidence": 0.3,
                "explanation": "No substantial evidence available from the cited source.",
                "evidence_span": None
            }
            state["confidence_score"] = 0.3
            return state

        try:
            chain = self.prompt | self.llm | self.parser
            result = chain.invoke({
                "claim_text": claim_text,
                "evidence_text": evidence
            })

            # Validate result
            if not result or not isinstance(result, dict):
                raise ValueError("Invalid LLM response")

            # Validate verdict
            valid_verdicts = ["supported", "partially_supported", "unsupported", "insufficient_evidence"]
            verdict = result.get("verdict", "insufficient_evidence")
            if verdict not in valid_verdicts:
                verdict = "insufficient_evidence"

            # Validate confidence
            confidence = float(result.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            state["verification_result"] = {
                "verdict": verdict,
                "confidence": confidence,
                "explanation": result.get("explanation", ""),
                "evidence_span": result.get("evidence_span")
            }
            state["confidence_score"] = confidence

        except Exception as e:
            print(f"[ClaimVerifier] LLM verification error: {e}")
            # Fallback to heuristic verification
            state["verification_result"] = self._heuristic_verify(claim_text, evidence)
            state["confidence_score"] = float(state["verification_result"]["confidence"])

        return state

    def _heuristic_verify(self, claim_text: str, evidence_text: str) -> dict:
        """Fallback heuristic verification"""
        claim_lower = claim_text.lower()
        evidence_lower = evidence_text.lower()

        # Extract key content words
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "being", "have", "has", "had", "do", "does", "did", "will",
                      "would", "could", "should", "may", "might", "must", "to",
                      "of", "in", "for", "on", "with", "at", "by", "from", "as",
                      "into", "through", "during", "before", "after", "above",
                      "below", "between", "under", "again", "further", "then",
                      "once", "here", "there", "when", "where", "why", "how",
                      "all", "each", "few", "more", "most", "other", "some",
                      "such", "no", "nor", "not", "only", "own", "same", "so",
                      "than", "too", "very", "just", "and", "but", "if", "or",
                      "because", "until", "while", "although", "though", "that",
                      "this", "these", "those", "it", "its", "we", "our", "they"}

        claim_words = set(w for w in claim_lower.split() if w not in stop_words and len(w) > 2)
        evidence_words = set(w for w in evidence_lower.split() if w not in stop_words and len(w) > 2)

        if not claim_words or not evidence_words:
            return {
                "verdict": "insufficient_evidence",
                "confidence": 0.3,
                "explanation": "Could not extract meaningful content for comparison.",
                "evidence_span": None
            }

        overlap = claim_words & evidence_words
        overlap_ratio = len(overlap) / max(len(claim_words), 1)

        if overlap_ratio >= 0.4:
            return {
                "verdict": "supported",
                "confidence": min(0.75, 0.5 + overlap_ratio),
                "explanation": f"Key terms from claim appear in evidence ({int(overlap_ratio * 100)}% keyword overlap).",
                "evidence_span": None
            }
        elif overlap_ratio >= 0.2:
            return {
                "verdict": "partially_supported",
                "confidence": 0.5,
                "explanation": f"Some key terms overlap but connection is partial ({int(overlap_ratio * 100)}% keyword overlap).",
                "evidence_span": None
            }
        else:
            return {
                "verdict": "insufficient_evidence",
                "confidence": 0.3,
                "explanation": f"Limited keyword overlap ({int(overlap_ratio * 100)}%).",
                "evidence_span": None
            }


# =============================================================================
# Agent 3: Trust Calculator - Computes confidence/trust scores
# =============================================================================

class TrustCalculator:
    """Calculates final confidence and trust scores"""

    def calculate(self, state: VerificationState) -> VerificationState:
        """Calculate final confidence score for this verification"""
        result = state.get("verification_result", {})
        verdict = result.get("verdict", "insufficient_evidence")
        llm_confidence = result.get("confidence", 0.5)

        # Base score from verdict
        base_score = VERDICT_SCORES.get(VerificationVerdict(verdict), 0.0)

        # Adjust by LLM confidence
        final_confidence = base_score * llm_confidence

        # Apply evidence quality bonus
        evidence = state.get("fetched_evidence", "")
        if evidence and len(evidence) > 200:
            final_confidence = min(1.0, final_confidence + 0.1)

        state["confidence_score"] = final_confidence
        return state


# =============================================================================
# LangGraph Workflow Builder
# =============================================================================

class VerificationWorkflow:
    """Builds and runs the LangGraph verification workflow"""

    def __init__(self):
        self.source_fetcher = SourceFetcher()
        self.claim_verifier = ClaimVerifier()
        self.trust_calculator = TrustCalculator()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(VerificationState)

        # Add nodes
        workflow.add_node("fetch_source", self.source_fetcher.fetch)
        workflow.add_node("verify_claim", self.claim_verifier.verify)
        workflow.add_node("calculate_trust", self.trust_calculator.calculate)

        # Set entry point
        workflow.set_entry_point("fetch_source")

        # Add edges
        workflow.add_edge("fetch_source", "verify_claim")
        workflow.add_edge("verify_claim", "calculate_trust")
        workflow.add_edge("calculate_trust", END)

        return workflow.compile()

    def run(self, claim_text: str, resolved_citation: ResolvedCitation,
            paper_full_text: Optional[str] = None) -> VerificationState:
        """Run the verification workflow"""
        initial_state = VerificationState(
            claim_id="",
            claim_text=claim_text,
            resolved_citation=resolved_citation,
            paper_full_text=paper_full_text,
            fetched_evidence="",
            verification_result=None,
            confidence_score=0.0,
            error=None
        )

        result = self.graph.invoke(initial_state)
        return result


# =============================================================================
# Main Entry Point - Integrates with existing verification_agent.py
# =============================================================================

def verify_claim_with_langgraph(
    claim_text: str,
    resolved_citation: ResolvedCitation,
    paper_full_text: Optional[str] = None,
    claim_id: str = ""
) -> VerificationResult:
    """
    Verify a single claim using LangGraph multi-agent workflow.

    Args:
        claim_text: The claim to verify
        resolved_citation: The resolved citation with metadata
        paper_full_text: Optional full text of the paper containing the claim
        claim_id: ID of the claim for tracking

    Returns:
        VerificationResult with verdict, confidence, and explanation
    """
    workflow = VerificationWorkflow()
    result_state = workflow.run(claim_text, resolved_citation, paper_full_text)

    verification_data = result_state.get("verification_result", {})
    confidence_score = result_state.get("confidence_score", 0.0)

    # Map verdict string to enum
    verdict_str = verification_data.get("verdict", "insufficient_evidence")
    try:
        verdict = VerificationVerdict(verdict_str)
    except ValueError:
        verdict = VerificationVerdict.INSUFFICIENT_EVIDENCE

    return VerificationResult(
        verification_id=f"v{hash(claim_id) % 1000 + 1}" if claim_id else "v1",
        claim_id=claim_id,
        claim_text=claim_text,
        ref_id=resolved_citation.ref_id,
        citation_title=resolved_citation.matched_title,
        resolution_status=resolved_citation.resolution_status,
        verdict=verdict,
        confidence=confidence_score,
        explanation=verification_data.get("explanation", "Verification completed"),
        evidence_span=verification_data.get("evidence_span"),
        used_text_source="fetched_evidence" if result_state.get("fetched_evidence") else "abstract"
    )


# =============================================================================
# Batch Verification - For processing multiple claims
# =============================================================================

def verify_claims_batch(
    parsed_paper: ParsedPaper,
    resolved_citations: ResolvedCitationsOutput
) -> List[VerificationResult]:
    """
    Verify all claims in a paper using the LangGraph workflow.

    Args:
        parsed_paper: Parsed paper with claims
        resolved_citations: Resolved citations output

    Returns:
        List of VerificationResult objects
    """
    # Build citation lookup
    citation_lookup = {
        c.ref_id: c for c in resolved_citations.resolved_citations
    }

    results = []
    workflow = VerificationWorkflow()

    for idx, claim in enumerate(parsed_paper.claims):
        if not claim.citations:
            continue

        primary_ref_id = claim.citations[0]
        resolved = citation_lookup.get(primary_ref_id)

        if resolved is None:
            results.append(VerificationResult(
                verification_id=f"v{idx + 1}",
                claim_id=claim.claim_id,
                claim_text=claim.claim_text,
                ref_id=primary_ref_id,
                citation_title=None,
                resolution_status=ResolutionStatus.UNRESOLVED,
                verdict=VerificationVerdict.UNRESOLVED,
                confidence=0.0,
                explanation="Citation could not be resolved to a real paper.",
                used_text_source="abstract"
            ))
            continue

        # Run verification workflow
        result_state = workflow.run(
            claim_text=claim.claim_text,
            resolved_citation=resolved,
            paper_full_text=parsed_paper.full_text,
            claim_id=claim.claim_id
        )

        verification_data = result_state.get("verification_result", {})
        confidence_score = result_state.get("confidence_score", 0.0)

        verdict_str = verification_data.get("verdict", "insufficient_evidence")
        try:
            verdict = VerificationVerdict(verdict_str)
        except ValueError:
            verdict = VerificationVerdict.INSUFFICIENT_EVIDENCE

        results.append(VerificationResult(
            verification_id=f"v{idx + 1}",
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            ref_id=resolved.ref_id,
            citation_title=resolved.matched_title,
            resolution_status=resolved.resolution_status,
            verdict=verdict,
            confidence=confidence_score,
            explanation=verification_data.get("explanation", "Verification completed"),
            evidence_span=verification_data.get("evidence_span"),
            used_text_source="fetched_evidence" if result_state.get("fetched_evidence") else "abstract"
        ))

    return results
