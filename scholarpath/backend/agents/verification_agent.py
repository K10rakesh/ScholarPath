# backend/agents/verification_agent.py
# Member 2 - Verification Agent
# Compares claims against cited paper abstracts using LLM to determine support

import json
import re
from typing import Optional

import ollama

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

# Using llama3.2 for better structured output - phi3 often returns empty responses
OLLAMA_MODEL = "llama3.2"

# Verdict scoring for trust calculation
VERDICT_SCORES = {
    VerificationVerdict.SUPPORTED: 1.0,
    VerificationVerdict.PARTIALLY_SUPPORTED: 0.6,
    VerificationVerdict.INSUFFICIENT_EVIDENCE: 0.3,
    VerificationVerdict.UNSUPPORTED: 0.0,
    VerificationVerdict.UNRESOLVED: 0.0,
}

# Trust status thresholds
TRUSTED_THRESHOLD = 75
CAUTION_THRESHOLD = 45


# =============================================================================
# Main entry point
# =============================================================================

def verify_claims(
    parsed_paper: ParsedPaper,
    resolved_citations: ResolvedCitationsOutput
) -> VerificationReportOutput:
    """
    Main entry point for claim verification.

    Args:
        parsed_paper: ParsedPaper from Member 1 (Contract 01)
        resolved_citations: ResolvedCitationsOutput from citation resolver (Contract 02)

    Returns:
        VerificationReportOutput (Contract 03)
    """
    doc_id = parsed_paper.doc_id
    verification_results = []
    errors = []

    # Build lookup: ref_id -> resolved citation
    citation_lookup = {
        c.ref_id: c for c in resolved_citations.resolved_citations
    }

    # Process each claim
    for idx, claim in enumerate(parsed_paper.claims):
        # Find the primary citation for this claim (use first one if multiple)
        if not claim.citations:
            errors.append({
                "code": "NO_CITATION",
                "message": f"Claim {claim.claim_id} has no citations"
            })
            continue

        primary_ref_id = claim.citations[0]
        resolved = citation_lookup.get(primary_ref_id)

        if resolved is None:
            errors.append({
                "code": "CITATION_NOT_FOUND",
                "message": f"Citation {primary_ref_id} not found in resolved citations"
            })
            verification_results.append(VerificationResult(
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

        # Get the evidence text - try multiple sources for better verification
        # Priority: full_text (if available) > abstract > source_url for web lookup
        evidence_text = resolved.abstract
        used_source = "abstract"

        # Check if we have additional evidence from the parsed paper's full text
        # that might contain more details about the cited work
        if parsed_paper.full_text and resolved.matched_title:
            # Look for mentions of this citation in the full text
            # This gives context about how the citation is used
            citation_mentions = _find_citation_context(parsed_paper.full_text, resolved.matched_title)
            if citation_mentions:
                evidence_text = f"{evidence_text or ''}\n\nContext from paper: {citation_mentions}"
                used_source = "abstract_with_context"

        if not evidence_text or len(evidence_text.strip()) < 50:
            # Try to fetch more content from source URL if available
            if resolved.source_url:
                fetched_content = _fetch_additional_evidence(resolved.source_url)
                if fetched_content:
                    evidence_text = fetched_content
                    used_source = "fetched_content"

        if not evidence_text or len(evidence_text.strip()) < 50:
            # No abstract available - mark as insufficient evidence
            verification_results.append(VerificationResult(
                verification_id=f"v{idx + 1}",
                claim_id=claim.claim_id,
                claim_text=claim.claim_text,
                ref_id=primary_ref_id,
                citation_title=resolved.matched_title,
                resolution_status=resolved.resolution_status,
                verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
                confidence=0.5,
                explanation="The cited paper was found but no abstract is available for comparison.",
                evidence_span=None,
                used_text_source="abstract"
            ))
            continue

        # Call LLM to verify the claim against the evidence
        result = _verify_claim_with_llm(claim, resolved, evidence_text, idx + 1)
        verification_results.append(result)

    # Calculate trust report
    trust_report = _calculate_trust_report(verification_results)

    return VerificationReportOutput(
        doc_id=doc_id,
        verification_results=verification_results,
        trust_report=trust_report,
        stats={
            "total_claims_checked": len(verification_results),
            "claims_with_resolved_citations": sum(
                1 for v in verification_results
                if v.resolution_status != ResolutionStatus.UNRESOLVED
            ),
            "claims_with_unresolved_citations": sum(
                1 for v in verification_results
                if v.resolution_status == ResolutionStatus.UNRESOLVED
            )
        },
        processing_status=ProcessingStatus.SUCCESS if not errors else ProcessingStatus.PARTIAL,
        errors=errors
    )


# =============================================================================
# Private helpers
# =============================================================================

def _verify_claim_with_llm(
    claim,
    resolved,
    evidence_text: str,
    verification_index: int
) -> VerificationResult:
    """
    Use LLM to verify if a claim is supported by the cited evidence.
    Falls back to heuristic verification if LLM is unavailable.
    """
    prompt = _build_verification_prompt(claim.claim_text, evidence_text)

    try:
        response = _call_llm(prompt)

        # Check if LLM returned empty (model unavailable)
        if not response or not response.strip():
            print(f"[verification_agent] LLM returned empty response, using heuristic fallback")
            return _verify_claim_heuristic(claim, resolved, verification_index)

        parsed = _parse_verification_response(response, claim, resolved, evidence_text)

        if parsed:
            return parsed

    except Exception as e:
        print(f"[verification_agent] LLM verification failed: {e}")

    # Fallback to heuristic verification
    return _verify_claim_heuristic(claim, resolved, verification_index)


def _build_verification_prompt(claim_text: str, evidence_text: str) -> str:
    """
    Build the prompt for claim verification.
    Presents claim and evidence side-by-side for comparison.
    """
    return f"""You are a fact-checking assistant for academic papers. Your task is to determine whether the given EVIDENCE supports the CLAIM.

Read both carefully and determine if the evidence actually proves, partially proves, or does not prove the claim.

CLAIM: {claim_text}

EVIDENCE (from cited paper abstract): {evidence_text}

Determine the verdict:
- "supported" = The evidence directly and clearly supports the claim
- "partially_supported" = The evidence is related but doesn't fully prove the claim, or only supports part of it
- "unsupported" = The evidence contradicts the claim or is irrelevant to it
- "insufficient_evidence" = The abstract doesn't contain enough information to judge

Respond in this EXACT JSON format (no markdown, no explanation):
{{
    "verdict": "supported" | "partially_supported" | "unsupported" | "insufficient_evidence",
    "confidence": 0.0-1.0,
    "explanation": "Brief explanation of your reasoning",
    "evidence_span": "Quote the specific part of the evidence that supports or contradicts"
}}

JSON:"""


def _call_llm(prompt: str) -> str:
    """
    Call local Ollama model for verification.
    Returns raw text response. Includes retry logic for reliability.
    """
    max_retries = 2
    last_error = None

    for attempt in range(max_retries):
        try:
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": "You are a precise fact-checking assistant. You ALWAYS respond with valid JSON only, no explanations or markdown."},
                    {"role": "user", "content": prompt}
                ],
                options={
                    "temperature": 0.1,  # Low temperature for consistent judgments
                    "top_p": 0.9,
                    "timeout": 60000  # 60 second timeout
                }
            )
            content = response["message"]["content"]
            if content and content.strip():
                return content
            print(f"[verification_agent] Attempt {attempt + 1} returned empty content")
            last_error = "Empty response"
        except Exception as e:
            print(f"[verification_agent] Ollama call attempt {attempt + 1} failed: {e}")
            last_error = e

    print(f"[verification_agent] All {max_retries} attempts failed")
    return ""


def _verify_claim_heuristic(
    claim,
    resolved,
    verification_index: int
) -> VerificationResult:
    """
    Fallback heuristic verification when LLM is unavailable.
    Makes a best-effort judgment based on text overlap and presence of evidence.
    """
    claim_text = claim.claim_text.lower()
    evidence_text = resolved.abstract.lower() if resolved.abstract else ""

    if not evidence_text:
        return VerificationResult(
            verification_id=f"v{verification_index}",
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            ref_id=resolved.ref_id,
            citation_title=resolved.matched_title,
            resolution_status=resolved.resolution_status,
            verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
            confidence=0.3,
            explanation="No abstract available for the cited paper to verify this claim.",
            evidence_span=None,
            used_text_source="abstract"
        )

    # Check for keyword overlap between claim and evidence
    claim_words = set(claim_text.split())
    evidence_words = set(evidence_text.split())

    # Filter out common stop words
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "and", "but", "if", "or", "because", "until", "while", "although", "though", "after", "before", "that", "this", "these", "those", "it", "its"}

    claim_content = claim_words - stop_words
    evidence_content = evidence_words - stop_words

    # Calculate overlap
    overlap = claim_content & evidence_content
    overlap_ratio = len(overlap) / max(len(claim_content), 1)

    # Make judgment based on overlap
    if overlap_ratio >= 0.4:
        verdict = VerificationVerdict.SUPPORTED
        confidence = min(0.7, 0.4 + overlap_ratio)
        explanation = f"Key terms from the claim appear in the cited evidence ({int(overlap_ratio * 100)}% keyword overlap)."
    elif overlap_ratio >= 0.2:
        verdict = VerificationVerdict.PARTIALLY_SUPPORTED
        confidence = 0.5
        explanation = f"Some key terms from the claim appear in the evidence, but the connection is partial ({int(overlap_ratio * 100)}% keyword overlap)."
    else:
        verdict = VerificationVerdict.INSUFFICIENT_EVIDENCE
        confidence = 0.3
        explanation = f"Limited keyword overlap ({int(overlap_ratio * 100)}%) suggests the evidence may not directly support this claim."

    return VerificationResult(
        verification_id=f"v{verification_index}",
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        ref_id=resolved.ref_id,
        citation_title=resolved.matched_title,
        resolution_status=resolved.resolution_status,
        verdict=verdict,
        confidence=confidence,
        explanation=explanation,
        evidence_span=None,
        used_text_source="abstract"
    )


def _parse_verification_response(
    raw: str,
    claim,
    resolved,
    evidence_text: str
) -> Optional[VerificationResult]:
    """
    Parse LLM response into a VerificationResult.
    Returns None if parsing fails.
    """
    try:
        # Clean up the response
        clean = raw.strip()
        clean = re.sub(r'^```json\s*', '', clean)
        clean = re.sub(r'^```\s*', '', clean)
        clean = re.sub(r'\s*```$', '', clean)
        clean = clean.strip()

        data = json.loads(clean)

        verdict_str = data.get("verdict", "insufficient_evidence")
        try:
            verdict = VerificationVerdict(verdict_str)
        except ValueError:
            verdict = VerificationVerdict.INSUFFICIENT_EVIDENCE

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

        return VerificationResult(
            verification_id=f"v{hash(claim.claim_id) % 1000 + 1}",
            claim_id=claim.claim_id,
            claim_text=claim.claim_text,
            ref_id=resolved.ref_id,
            citation_title=resolved.matched_title,
            resolution_status=resolved.resolution_status,
            verdict=verdict,
            confidence=confidence,
            explanation=data.get("explanation", "No explanation provided"),
            evidence_span=data.get("evidence_span"),
            used_text_source="abstract"
        )

    except json.JSONDecodeError as e:
        print(f"[verification_agent] JSON decode error: {e}")
        return None
    except Exception as e:
        print(f"[verification_agent] Parse error: {e}")
        return None


def _find_citation_context(full_text: str, matched_title: str) -> str:
    """
    Find where in the full text a cited paper is mentioned and extract context.
    This helps verify claims by understanding how the citation is used.
    """
    if not matched_title or len(matched_title) < 5:
        return ""

    # Look for partial title matches (first 3-4 words of title)
    title_words = matched_title.split()[:4]
    title_fragment = " ".join(title_words)

    # Search for title fragment in full text (case insensitive)
    import re
    pattern = re.compile(re.escape(title_fragment), re.IGNORECASE)
    matches = list(pattern.finditer(full_text))

    if not matches:
        return ""

    # Extract context around the first match (window of ~200 chars)
    match = matches[0]
    start = max(0, match.start() - 100)
    end = min(len(full_text), match.end() + 100)

    context = full_text[start:end]
    # Clean up whitespace
    context = " ".join(context.split())

    return context


def _fetch_additional_evidence(source_url: str) -> str:
    """
    Fetch additional content from the source URL.
    For now, this is a placeholder - in production, use a proper web scraper.
    """
    try:
        import httpx
        # Only fetch from trusted sources (arxiv, semanticscholar)
        if "arxiv.org" in source_url or "semanticscholar.org" in source_url:
            with httpx.Client(timeout=5.0, follow_redirects=True) as client:
                response = client.get(source_url)
                if response.status_code == 200:
                    # Extract meta description or first paragraph
                    html = response.text
                    # Simple extraction - look for meta description
                    import re
                    meta_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
                    if meta_match:
                        return meta_match.group(1)
                    # Fallback: extract first 500 chars of visible text
                    text = re.sub(r'<[^>]+>', ' ', html)
                    return text[:500].strip()
    except Exception as e:
        print(f"[verification_agent] Failed to fetch additional evidence: {e}")
    return ""


def _calculate_trust_report(results: list[VerificationResult]) -> TrustReport:
    """
    Calculate the overall trust score and status from verification results.
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

    # Count verdicts
    supported_count = sum(1 for r in results if r.verdict == VerificationVerdict.SUPPORTED)
    partially_supported_count = sum(1 for r in results if r.verdict == VerificationVerdict.PARTIALLY_SUPPORTED)
    unsupported_count = sum(1 for r in results if r.verdict == VerificationVerdict.UNSUPPORTED)
    insufficient_count = sum(1 for r in results if r.verdict == VerificationVerdict.INSUFFICIENT_EVIDENCE)
    unresolved_count = sum(1 for r in results if r.verdict == VerificationVerdict.UNRESOLVED)

    # Calculate weighted score
    total_score = sum(VERDICT_SCORES[r.verdict] for r in results)
    average_score = total_score / len(results)
    trust_score = int(average_score * 100)

    # Determine status
    if trust_score >= TRUSTED_THRESHOLD:
        status = TrustStatus.TRUSTED
        summary = f"Most key claims are supported or partially supported by their cited references."
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
