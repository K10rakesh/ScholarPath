# =============================================================================
# backend/agents/claim_extractor.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   Phase 2 of the PDF parsing pipeline. Takes the citation-bearing sentences
#   found by pdf_parser.py and uses a local Ollama LLM (llama3.2) to identify
#   which sentences make VERIFIABLE FACTUAL CLAIMS backed by citations.
#
#   Implements a robust 3-tier extraction strategy:
#     1. LLM extraction (primary) — uses llama3.2 via Ollama for semantic understanding
#     2. Retry on bad JSON (automatic) — one retry with stricter prompt instructions
#     3. Heuristic fallback (if LLM completely fails) — keyword/regex-based classifier
#
#   Sentences are processed in batches of 5 to keep each LLM call small
#   and prevent JSON truncation in smaller local models.
#
# CONNECTED TO:
#   ← backend/agents/pdf_parser.py         (calls extract_claims())
#   → backend/prompts/claim_extraction.py  (imports the LLM prompt template)
#   → backend/schemas.py                   (returns list[Claim])
# =============================================================================

import json
import os
import re
import ollama

from backend.schemas import Claim, Section
from backend.prompts.claim_extraction import CLAIM_EXTRACTION_PROMPT

# llama3.2 is used instead of phi3 because phi3 frequently returns empty responses
# for structured JSON tasks. llama3.2 has better instruction-following capability.
OLLAMA_MODEL = "llama3.2:1b"


def extract_claims(
    citation_sentences: list[dict],
    sections: list[Section]
) -> list[Claim]:
    """
    MAIN ENTRY POINT.
    Takes citation sentences from pdf_parser + section list.
    Returns a flat list of Claim objects.

    PROCESSING STRATEGY:
      1. Build a sentence_index → section info lookup (for filling Claim.section)
      2. Split sentences into batches of 5 (prevents JSON truncation in LLM output)
      3. Process each batch through the LLM
      4. If LLM produced nothing → fallback to heuristic extraction
      5. Deduplicate claims by claim_text (safety net for overlapping batches)

    WHY BATCH SIZE 5:
      Larger batches often produce truncated JSON responses from smaller LLMs.
      5 sentences produces roughly 500-800 tokens of output — well within limits.
    """
    if not citation_sentences:
        citation_sentences = []

    # Build sentence_index → {heading, section_id} mapping
    # Used to fill in section info for each claim without character offset tracking
    section_lookup = _build_section_lookup(citation_sentences, sections)

    # Author-year style citations bhi dhundo (Vaswani et al., 2017)
    author_year_sentences = _extract_author_year_sentences(citation_sentences)
    
    # Keyword-based claims bhi dhundo (We show, Results demonstrate, etc.)
    keyword_sentences = _extract_keyword_sentences(citation_sentences)
    
    # Sab merge karo — duplicates baad mein hatenge
    all_sentences = citation_sentences + author_year_sentences + keyword_sentences
    
    # Deduplicate by sentence text
    seen_texts = set()
    unique_sentences = []
    for s in all_sentences:
        if s["sentence"] not in seen_texts:
            seen_texts.add(s["sentence"])
            unique_sentences.append(s)
    
    citation_sentences = unique_sentences

    # Split all citation sentences into chunks of 5
    batches = [
        citation_sentences[i:i + 5]
        for i in range(0, len(citation_sentences), 5)
    ]
    all_claims = []
    global_counter = 1   # claim IDs (c1, c2, c3...) must be unique across all batches
    llm_success = False

    for batch in batches:
        claims, count = _process_batch(batch, section_lookup, global_counter)
        if count > 0:
            llm_success = True
        all_claims.extend(claims)
        global_counter += count   # advance counter so next batch picks up where this left off

    # If LLM extraction produced nothing at all, fall back to heuristic method
    if not llm_success or not all_claims:
        print("[claim_extractor] LLM extraction returned no claims, using heuristic fallback")
        heuristic_claims = _extract_claims_heuristic(citation_sentences, sections)
        if heuristic_claims:
            return heuristic_claims

    # Deduplicate by claim_text — safety net in case batches produce overlapping claims
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
    Processes one batch of ≤5 citation sentences through the LLM.
    Returns (claims_list, count_of_valid_claims).

    RETRY LOGIC:
      If the first LLM call returns bad JSON (parse fails), we retry ONCE with
      a stricter prompt that explicitly tells the model its previous response failed.
      After two failures, the batch is silently skipped (not a hard crash).

    WHY NOT RETRY MORE:
      More than 2 attempts would make the pipeline too slow.
      The heuristic fallback handles overall failure at the top level.
    """
    # Format each sentence with its index prefix for the LLM prompt
    sentences_text = "\n".join(
        f"[idx:{s['sentence_index']}] {s['sentence']}"
        for s in batch
    )
    prompt = CLAIM_EXTRACTION_PROMPT.format(sentences=sentences_text)

    # First attempt
    raw = _call_llm(prompt)
    claims = _parse_response(raw, section_lookup, start_counter)

    if claims is None:
        # JSON parsing failed — retry with an explicit error message in the prompt
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


def _call_llm(prompt: str) -> str:
    """
    Makes a chat call to the local Ollama llama3.2 model.
    Returns the raw text response. Never raises — returns "[]" on failure.

    WHY LOCAL OLLAMA:
      - Zero API cost (important for hackathon/demo)
      - Works offline
      - No rate limits for local inference

    PARAMETERS:
      temperature=0   → deterministic output, essential for JSON parsing
      num_predict=3000 → max tokens to generate (enough for 5 claim objects)
      timeout=60000   → 60 second timeout (llama3.2 can be slow on CPU)

    RETRY: 2 attempts with failure logging between each.
    """
    max_retries = 2
    last_error = None

    for attempt in range(max_retries):
        try:
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    # System message enforces JSON-only output — critical for parsing
                    {"role": "system", "content": "You are a precise claim extraction assistant. You ALWAYS respond with valid JSON arrays only, no explanations or markdown."},
                    {"role": "user", "content": prompt}
                ],
                options={
                    "temperature": 0,       # deterministic — same input always same output
                    "top_p": 0.9,
                    "timeout": 60000,       # 60s — local LLM can be slow on CPU
                    "num_predict": 3000     # max tokens for 5 claim JSON objects
                }
            )
            content = response["message"]["content"]
            if content and content.strip():
                return content
            print(f"[claim_extractor] Attempt {attempt + 1} returned empty content")
            last_error = "Empty response"
        except Exception as e:
            print(f"[claim_extractor] Ollama call attempt {attempt + 1} failed: {e}")
            last_error = e

    print(f"[claim_extractor] All {max_retries} attempts failed")
    print("  → Is Ollama running? Start it with: ollama serve")
    return "[]"  # Return empty array so _parse_response returns [] not None


def _extract_claims_heuristic(
    citation_sentences: list[dict],
    sections: list[Section]
) -> list[Claim]:
    """
    FALLBACK: Heuristic claim extraction when Ollama is unavailable or unresponsive.
    Uses keyword matching and citation marker detection instead of LLM understanding.

    APPROACH:
      - Takes every citation sentence (already filtered to contain [N] markers)
      - Skips sentences that look speculative or future-work oriented
      - Classifies the remainder as claims based on keyword presence
      - Assigns priority and claim_type based on vocabulary

    WHY NEEDED:
      Demo robustness — if Ollama isn't running at demo time, the system still
      produces some output rather than returning an empty claims list.

    LIMITATIONS:
      Much lower precision than LLM extraction — will include noise.
      But it's better than returning nothing.
    """
    section_lookup = _build_section_lookup(citation_sentences, sections)
    claims = []

    for i, sent in enumerate(citation_sentences):
        sentence = sent.get("sentence", "")
        sentence_idx = sent.get("sentence_index", i)

        # Only process sentences with citation markers
        # [1] style citations
        citation_markers = re.findall(r'\[\d+(?:,\s*\d+)*\]', sentence)
        
        # (Smith et al., 2020) style citations
        author_year_markers = re.findall(
            r'\([A-Z][a-z]+(?:\s+et al\.?)?,?\s+\d{4}\)', sentence
        )
        
        # Keyword-based claims (no citation needed)
        claim_keywords = [
            "we show", "we propose", "we demonstrate", "we present",
            "results show", "experiments show", "our method", "our approach",
            "outperforms", "achieves state-of-the-art", "improves over",
            "we find that", "analysis shows", "we conclude", "we introduce",
            "results demonstrate", "our model", "we evaluate"
        ]
        has_claim_keyword = any(kw in lower for kw in claim_keywords)
        
        all_markers = citation_markers + author_year_markers
        
        # Koi bhi ek hona chahiye — citation ya keyword
        if not all_markers and not has_claim_keyword:
            continue
            
        citation_markers = all_markers if all_markers else ["keyword-claim"]

        # Skip speculative/hedging sentences — these are not verifiable claims
        lower = sentence.lower()
        if any(kw in lower for kw in [
            "future work", "should", "might", "could", "we believe",
            "it seems", "limitation", "one direction"
        ]):
            continue

        # Get section info from lookup
        sec_info = section_lookup.get(sentence_idx, {})
        section_heading = sec_info.get("heading", "Unknown")
        section_id = sec_info.get("section_id", "s0")

        # Classify claim type and priority based on verb/keyword presence
        if "result" in lower or "achieve" in lower or "outperform" in lower:
            claim_type = "result"
            priority = "high"
        elif "method" in lower or "approach" in lower or "propose" in lower:
            claim_type = "method"
            priority = "high"
        elif "compare" in lower or "better" in lower or "than" in lower:
            claim_type = "comparative"
            priority = "high"
        else:
            claim_type = "background"
            priority = "medium"

        claims.append(Claim(
            claim_id=f"c{i + 1}",
            claim_text=sentence,
            citations=citation_markers,
            section=section_heading,
            section_id=section_id,
            priority=priority,
            claim_type=claim_type,
            sentence_index=sentence_idx
        ))

    return claims


def _parse_response(
    raw: str,
    section_lookup: dict,
    start_counter: int
) -> list[Claim] | None:
    """
    Parses raw LLM text into a list of Claim objects.
    Returns None if JSON is unparseable — signals the caller to retry.

    HANDLES COMMON LLM QUIRKS:
      - Markdown code fences: ```json ... ``` → stripped
      - Single dict instead of array: {"claims": [...]} → unwrapped
      - Missing optional fields → filled with safe defaults
      - Invalid Claim items → individually skipped, others kept

    WHY RETURN None instead of []:
      Empty list [] is a valid result (no claims in this batch).
      None specifically signals "JSON was malformed, try again."
    """
    try:
        # Strip markdown fences that models sometimes add despite instruction
        # Strip markdown fences that models sometimes add despite instruction
        clean = raw.strip()
        clean = re.sub(r'^```json\s*', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'^```\s*', '', clean, flags=re.MULTILINE)
        clean = re.sub(r'\s*```$', '', clean, flags=re.MULTILINE)
        clean = clean.strip()

        # Extract just the first JSON array — model sometimes outputs extra text after
        match = re.search(r'\[.*?\]', clean, re.DOTALL)
        if match:
            clean = match.group(0)

        data = json.loads(clean)

        # Handle edge case: model returned a dict instead of an array
        if isinstance(data, dict):
            if len(data.keys()) == 1 and isinstance(list(data.values())[0], list):
                # e.g. {"claims": [...]} → unwrap to just the list
                data = list(data.values())[0]
            else:
                data = [data]   # single claim as dict → wrap in list

        claims = []
        for i, item in enumerate(data):
            # Assign a globally unique claim_id (continues from previous batches)
            item["claim_id"] = f"c{start_counter + i}"

            # Fill in section info from lookup if the LLM left it blank
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
                claims.append(Claim(**item))  # Pydantic validates types
            except Exception as e:
                # Skip individual bad items rather than failing the whole batch
                print(f"[claim_extractor] Skipping invalid claim item: {e}")
                continue
            
        # Filter garbage claims
        claims = [c for c in claims if len(c.claim_text.split()) > 8]
        claims = [c for c in claims if not c.claim_text.strip().startswith("BACKGROUND")]
        claims = [c for c in claims if not c.claim_text.strip().startswith("how to")]
        return claims

        

    except json.JSONDecodeError as e:
        print(f"[claim_extractor] JSON decode error: {e}")
        return None   # Signals caller to retry


def _build_section_lookup(
    citation_sentences: list[dict],
    sections: list[Section]
) -> dict:
    """
    Maps sentence_index → section info dict.

    APPROACH:
      Since we don't have character offsets on individual sentences, we spread
      the sentence indexes proportionally across sections. If there are 100
      sentences and 4 sections, sentences 0-24 → s1, 25-49 → s2, etc.

    This is an approximation — not perfectly accurate, but avoids expensive
    re-matching of sentences against section character ranges.

    Returns: {sentence_index: {"heading": str, "section_id": str}}
    """
    if not sections or not citation_sentences:
        return {}

    total = max(s["sentence_index"] for s in citation_sentences) + 1
    per_section = total / len(sections)  # approx sentences per section
    lookup = {}

    for sent in citation_sentences:
        idx = sent["sentence_index"]
        # Clamp to last section index to handle edge cases
        section_index = min(int(idx / per_section), len(sections) - 1)
        sec = sections[section_index]
        lookup[idx] = {
            "heading": sec.heading,
            "section_id": sec.section_id
        }

    return lookup

def _extract_author_year_sentences(citation_sentences: list[dict]) -> list[dict]:
    """
    Author-year style citations dhundta hai jaise (Vaswani et al., 2017)
    PDF ke full text se — jo [N] style mein nahi hain.
    """
    author_year_pattern = re.compile(
        r'\([A-Z][a-z]+(?:\s+et al\.?)?,?\s+\d{4}\)'
    )
    
    new_sentences = []
    max_idx = max((s["sentence_index"] for s in citation_sentences), default=0)
    
    for i, sent in enumerate(citation_sentences):
        sentence = sent.get("sentence", "")
        if author_year_pattern.search(sentence):
            # Already in list toh skip
            if not re.findall(r'\[\d+\]', sentence):
                new_sentences.append({
                    "sentence": sentence,
                    "sentence_index": max_idx + i + 1
                })
    
    return new_sentences


def _extract_keyword_sentences(citation_sentences: list[dict]) -> list[dict]:
    """
    Research claim keywords dhundta hai jaise 'We show', 'Results demonstrate'
    Citation marker na ho tab bhi claim extract karta hai.
    """
    claim_keywords = [
        "we show that", "we propose", "we demonstrate", "we present",
        "results show", "experiments show", "our method", "our approach",
        "outperforms", "achieves state-of-the-art", "improves over",
        "we find that", "analysis shows", "we conclude", "we introduce",
        "results demonstrate", "our model achieves", "we evaluate",
        "significantly better", "superior to", "baseline by"
    ]
    
    skip_keywords = [
        "future work", "should", "might", "could", "we believe",
        "it seems", "limitation", "one direction", "we hope"
    ]
    
    new_sentences = []
    max_idx = max((s["sentence_index"] for s in citation_sentences), default=0)
    
    for i, sent in enumerate(citation_sentences):
        sentence = sent.get("sentence", "")
        lower = sentence.lower()
        
        # Skip karo agar pehle se citation hai
        if re.findall(r'\[\d+\]', sentence):
            continue
            
        # Skip speculative sentences
        if any(kw in lower for kw in skip_keywords):
            continue
        
        # Check claim keywords
        if any(kw in lower for kw in claim_keywords):
            if len(sentence.split()) > 8:  # Minimum length
                new_sentences.append({
                    "sentence": sentence,
                    "sentence_index": max_idx + len(citation_sentences) + i + 1
                })
    
    return new_sentences
