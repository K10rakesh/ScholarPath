    # =============================================================================
# backend/agents/langgraph_verification.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   Implements the LangGraph multi-agent verification workflow. This is the
#   core of ScholarPath's "Trust Gate" — the pipeline that determines whether
#   a cited paper actually supports the claim made about it.
#
#   LANGGRAPH GRAPH (3 nodes, linear flow):
#
#     VerificationState (shared dict)
#           │
#           ▼
#     [fetch_source]    ← SourceFetcher: uses pre-fetched abstract (no extra network round-trip)
#           │
#           ▼       
#     [verify_claim]    ← ClaimVerifier: ChatOllama + LangChain prompt → JSON verdict
#           │
#           ▼
#     [calculate_trust] ← TrustCalculator: final_score = base_score × llm_confidence
#           │
#           ▼
#          END  →  VerificationResult returned to verification_agent.py
#
#   WHY LANGGRAPH:
#     - Clean state machine with explicit node transitions
#     - Easy to add new agents (e.g., web search, full-text fetch) later
#     - State is shared and typed (TypedDict), preventing data loss between nodes
#     - Observability: each node logs its step
#
# CONNECTED TO:
#   ← backend/agents/verification_agent.py  (calls verify_claim_with_langgraph())
#   → backend/schemas_member2.py            (output: VerificationResult)
# =============================================================================

import re
import json
import httpx
import os
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
Ollama="llama3.2:1b"
VERDICT_SCORES = {
    VerificationVerdict.SUPPORTED: 85.0,
    VerificationVerdict.PARTIALLY_SUPPORTED: 55.0,
    VerificationVerdict.INSUFFICIENT_EVIDENCE: 30.0,
        VerificationVerdict.UNSUPPORTED: 15.0,
    VerificationVerdict.UNRESOLVED: 0.0,
    }

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
        """Fetch evidence from the cited source. Overwhelmingly relies on the pre-fetched abstract to save extreme network delays."""
        citation = state["resolved_citation"]

        # Priority 1: Use pre-resolved abstract avoiding network latency entirely!
        if citation.abstract and len(citation.abstract.strip()) > 10:
            state["fetched_evidence"] = citation.abstract
            return state

        # Priority 2: Use matching properties if available
        if citation.matched_title:
            try:
                state["fetched_evidence"] = citation.matched_title
                return state
            except Exception:
                pass

        state["fetched_evidence"] = ""
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
        self.llm = ChatOllama(
            model=OLLAMA_MODEL, 
            temperature=0.1,
            base_url=f"http://{os.environ.get('OLLAMA_HOST', '127.0.0.1:11434')}"
        )
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
    "confidence_score": 0.0 to 100.0,
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
                "confidence_score": 30.0,
                "explanation": "No substantial evidence available from the cited source.",
                "evidence_span": None
            }
            state["confidence_score"] = 30.0
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
            confidence_score = float(result.get("confidence_score", result.get("confidence", 50.0)))
            if confidence_score <= 1.0 and confidence_score > 0.0 and "confidence_score" not in result:
                confidence_score = confidence_score * 100.0
            confidence_score = max(0.0, min(100.0, confidence_score))

            state["verification_result"] = {
                "verdict": verdict,
                "confidence_score": confidence_score,
                "explanation": result.get("explanation", ""),
                "evidence_span": result.get("evidence_span")
            }
            state["confidence_score"] = confidence_score

        except Exception as e:
            print(f"[ClaimVerifier] LLM verification error: {e}")
            state["verification_result"] = {
                "verdict": "insufficient_evidence",
                "confidence_score": 30.0,
                "explanation": "LLM verification agent failed to respond.",
                "evidence_span": None
            }
            state["confidence_score"] = 30.0

        return state


# =============================================================================
# Agent 3: Trust Calculator - Computes confidence/trust scores
# =============================================================================

class TrustCalculator:
    """Calculates final confidence and trust scores"""

    def calculate(self, state: VerificationState) -> VerificationState:
        """Calculate final confidence score for this verification"""
        result = state.get("verification_result", {})
        verdict = result.get("verdict", "insufficient_evidence")
        llm_confidence = result.get("confidence_score", 50.0)

        base_score = VERDICT_SCORES.get(VerificationVerdict(verdict), 30.0)
        final_confidence = (base_score + llm_confidence) / 2.0

        # Evidence quality bonus
        evidence = state.get("fetched_evidence", "")
        if evidence and len(evidence) > 200:
            final_confidence = min(100.0, final_confidence + 5.0)

        state["confidence_score"] = round(final_confidence, 2)
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
        VerificationResult with verdict, confidence score, and explanation
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
        confidence_score=confidence_score,
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
                confidence_score=0.0,
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
            confidence_score=confidence_score,
            explanation=verification_data.get("explanation", "Verification completed"),
            evidence_span=verification_data.get("evidence_span"),
            used_text_source="fetched_evidence" if result_state.get("fetched_evidence") else "abstract"
        ))

    return results
