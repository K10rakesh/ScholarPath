# backend/agents/claim_extractor.py

import json
import os
import re
import ollama

from backend.schemas import Claim, Section
from backend.prompts.claim_extraction import CLAIM_EXTRACTION_PROMPT

# OLLAMA_MODEL = "llama3.2"
OLLAMA_MODEL = "phi3"
def extract_claims(
    citation_sentences: list[dict],
    sections: list[Section]
) -> list[Claim]:
    """
    Main entry point.
    Takes citation sentences from pdf_parser + section list.
    Returns a flat list of Claim objects.
    """
    if not citation_sentences:
        return []

    # Build sentence_index → section info lookup
    section_lookup = _build_section_lookup(citation_sentences, sections)

    # Split into batches of 10 (keeps each LLM call manageable)
    batches = [
        citation_sentences[i:i + 10]
        for i in range(0, len(citation_sentences), 10)
    ]

    all_claims = []
    global_counter = 1  # claim IDs are globally unique: c1, c2, c3...

    for batch in batches:
        claims, count = _process_batch(batch, section_lookup, global_counter)
        all_claims.extend(claims)
        global_counter += count

    # Deduplicate by claim_text — safety net for overlapping batches
    seen = set()
    unique = []
    for claim in all_claims:
        if claim.claim_text not in seen:
            seen.add(claim.claim_text)
            unique.append(claim)

    return unique


# ── Private helpers ────────────────────────────────────────────────────────────

def _process_batch(
    batch: list[dict],
    section_lookup: dict,
    start_counter: int
) -> tuple[list[Claim], int]:
    """
    Processes one batch of ≤10 sentences.
    Returns (claims, count_of_valid_claims).
    Retries once on bad JSON. Fails gracefully.
    """
    sentences_text = "\n".join(
        f"[idx:{s['sentence_index']}] {s['sentence']}"
        for s in batch
    )
    prompt = CLAIM_EXTRACTION_PROMPT.format(sentences=sentences_text)

    # First attempt
    raw = _call_llm(prompt)
    claims = _parse_response(raw, section_lookup, start_counter)

    if claims is None:
        # Bad JSON — retry once with a stricter prompt
        print("[claim_extractor] Parse failed, retrying...")
        retry_prompt = (
            prompt +
            "\n\nIMPORTANT: Your previous response could not be parsed as JSON. "
            "Return ONLY a valid JSON array. No markdown. No explanation."
        )
        raw = _call_llm(retry_prompt)
        claims = _parse_response(raw, section_lookup, start_counter)

    if claims is None:
        print("[claim_extractor] Both attempts failed. Skipping batch.")
        return [], 0

    return claims, len(claims)


# def _call_llm(prompt: str) -> str:
#     """
#     Single Anthropic API call. Temperature=0 for deterministic output.
#     Returns raw text. Never raises — returns "[]" on failure.
#     """
#     try:
#         response = client.messages.create(
#             model="claude-opus-4-6",
#             max_tokens=2000,
#             temperature=0,
#             messages=[{"role": "user", "content": prompt}]
#         )
#         return response.content[0].text
#     except Exception as e:
#         print(f"[claim_extractor] LLM call failed: {e}")
#         return "[]"

def _call_llm(prompt: str) -> str:
    """
    Calls local Ollama model. Completely free, no internet needed.
    Returns raw text. Never raises — returns "[]" on failure.
    """
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0}  # deterministic output
        )
        return response["message"]["content"]

    except Exception as e:
        print(f"[claim_extractor] Ollama call failed: {e}")
        print("  → Is Ollama running? Start it with: ollama serve")
        return "[]"
    
def _parse_response(
    raw: str,
    section_lookup: dict,
    start_counter: int
) -> list[Claim] | None:
    """
    Parses raw LLM text into Claim objects.
    Returns None if JSON is unparseable (signals caller to retry).
    """
    try:
        # Strip markdown fences the model sometimes adds despite instructions
        clean = raw.strip()
        clean = re.sub(r'^```json\s*', '', clean)
        clean = re.sub(r'^```\s*', '', clean)
        clean = re.sub(r'\s*```$', '', clean)
        clean = clean.strip()

        data = json.loads(clean)

        # Handle edge case: model returned a single dict instead of array
        if isinstance(data, dict):
            data = [data]

        claims = []
        for i, item in enumerate(data):
            # Assign globally unique claim_id
            item["claim_id"] = f"c{start_counter + i}"

            # Fill in section info from lookup if model left it blank
            idx = item.get("sentence_index", -1)
            if idx in section_lookup:
                if not item.get("section"):
                    item["section"] = section_lookup[idx]["heading"]
                if not item.get("section_id"):
                    item["section_id"] = section_lookup[idx]["section_id"]

            # Safe defaults for any missing optional fields
            item.setdefault("section", "Unknown")
            item.setdefault("section_id", "s0")
            item.setdefault("priority", "medium")
            item.setdefault("claim_type", "background")
            item.setdefault("sentence_index", 0)

            try:
                claims.append(Claim(**item))
            except Exception as e:
                print(f"[claim_extractor] Skipping invalid claim item: {e}")
                continue

        return claims

    except json.JSONDecodeError as e:
        print(f"[claim_extractor] JSON decode error: {e}")
        return None  # tells caller to retry


def _build_section_lookup(
    citation_sentences: list[dict],
    sections: list[Section]
) -> dict:
    """
    Maps sentence_index → section info.
    Divides sentences proportionally across sections since we have no
    character offsets on individual sentences.

    Returns: {sentence_index: {"heading": str, "section_id": str}}
    """
    if not sections or not citation_sentences:
        return {}

    total = max(s["sentence_index"] for s in citation_sentences) + 1
    per_section = total / len(sections)
    lookup = {}

    for sent in citation_sentences:
        idx = sent["sentence_index"]
        section_index = min(int(idx / per_section), len(sections) - 1)
        sec = sections[section_index]
        lookup[idx] = {
            "heading": sec.heading,
            "section_id": sec.section_id
        }

    return lookup