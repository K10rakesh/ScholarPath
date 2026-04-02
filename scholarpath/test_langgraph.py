import sys
import os

sys.path.append(r"c:\Users\venom\Desktop\scholarpath\ScholarPath")

from backend.schemas_member2 import ResolvedCitation, ResolutionStatus
from backend.agents.langgraph_verification import verify_claim_with_langgraph

claim_text = "Transformers rely heavily on attention mechanisms."
resolved_citation = ResolvedCitation(
    ref_id="[1]",
    resolution_status=ResolutionStatus.RESOLVED,
    abstract="The Transformer is an architecture that relies purely on attention mechanisms.",
    raw_text="Attention is All You Need"
)

try:
    res = verify_claim_with_langgraph(claim_text, resolved_citation)
    print("Verdict:", res.verdict)
    print("Confidence:", res.confidence)
    print("Explanation:", res.explanation)
except Exception as e:
    print("Error:", e)
