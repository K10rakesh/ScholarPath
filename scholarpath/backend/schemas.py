# backend/schemas.py
# These Pydantic models define the exact shape of our output contract.
# Member 2 codes against these shapes — do not rename any keys.

from pydantic import BaseModel, model_validator
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