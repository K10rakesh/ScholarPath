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

# OLLAMA_MODEL = "llama3.2"
OLLAMA_MODEL = "phi3"  # Lighter model, works well for structured tasks

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

        # Get the evidence text (abstract or full text)
        evidence_text = resolved.abstract
        used_source = "abstract"

        if not evidence_text:
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
    """
    prompt = _build_verification_prompt(claim.claim_text, evidence_text)

    try:
        response = _call_llm(prompt)
        parsed = _parse_verification_response(response, claim, resolved, evidence_text)

        if parsed:
            return parsed

    except Exception as e:
        print(f"[verification_agent] LLM verification failed: {e}")

    # Fallback: return insufficient evidence
    return VerificationResult(
        verification_id=f"v{verification_index}",
        claim_id=claim.claim_id,
        claim_text=claim.claim_text,
        ref_id=resolved.ref_id,
        citation_title=resolved.matched_title,
        resolution_status=resolved.resolution_status,
        verdict=VerificationVerdict.INSUFFICIENT_EVIDENCE,
        confidence=0.3,
        explanation="Could not determine support level from the available evidence.",
        evidence_span=None,
        used_text_source="abstract"
    )


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
    Returns raw text response.
    """
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.1}  # Low temperature for consistent judgments
        )
        return response["message"]["content"]
    except Exception as e:
        print(f"[verification_agent] Ollama call failed: {e}")
        return ""


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
