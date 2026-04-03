# =============================================================================
# backend/utils/citation_patterns.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   Pure utility module containing all regex-based text manipulation logic.
#   No LLM calls, no I/O, no database. Just string → structured data.
#   Called exclusively by pdf_parser.py.
#
# These functions implement the structural parsing layer — before any LLM
# analysis, we need to segment the paper and identify where citations appear.
#
# CONNECTED TO:
#   ← backend/agents/pdf_parser.py  (imports all 4 main functions)
#   → backend/schemas.py             (returns Reference objects)
# =============================================================================

import re
from backend.schemas import Reference


# ─── Regex Patterns (compiled at module level for performance) ─────────────────

# Matches citation markers in the body text:
#   [1]     — single citation
#   [1,2]   — multiple citations in one marker
#   [1-3]   — citation range
# The inner group captures what's between the brackets for further parsing.
NUMBERED_CITATION = re.compile(r'\[(\d+(?:[,\-]\d+)*)\]')

# Matches standard academic section headings.
# IGNORECASE so "introduction", "INTRODUCTION", "Introduction" all match.
# MULTILINE so ^ matches at the start of each line (not just the whole string).
SECTION_HEADING = re.compile(
    r'^(Abstract|Introduction|Background|Related Work|'
    r'Methodology|Method|Model|Architecture|'
    r'Experiments?|Results?|Discussion|Conclusion|'
    r'Limitations?|References?|Bibliography|Appendix)',
    re.IGNORECASE | re.MULTILINE
)

# Matches numbered bibliography entries: [1] full citation text...
# DOTALL so '.' matches newlines (multi-line bibliography entries).
# Uses a lazy match (.+?) so it stops at the next [N] or end-of-string.
BIBLIOGRAPHY_ENTRY = re.compile(
    r'(\[\d+\])\s+(.+?)(?=\[\d+\]|\Z)',
    re.DOTALL
)

# Matches the heading that starts the references section.
# We use the LAST match in the document to avoid false positives in body text
# (e.g., "see References [3] for details").
REFERENCES_SECTION = re.compile(
    r'\n\s*(References|Bibliography|Works Cited)\s*\n',
    re.IGNORECASE
)


# ─── Functions ────────────────────────────────────────────────────────────────

def find_citation_markers(sentence: str) -> list[str]:
    """
    Extracts all citation markers from a sentence and returns them as a
    deduplicated list of canonical "[N]" format strings.

    HANDLES COMPLEX CITATION FORMS:
      [1]     → ["[1]"]
      [1,2]   → ["[1]", "[2]"]     (comma list → expand each)
      [1-3]   → ["[1]", "[2]", "[3]"]  (range → expand all)
      [1,3-5] → ["[1]", "[3]", "[4]", "[5]"]  (mixed)

    WHY EXPAND:
      Downstream code (claim_extractor, citation_resolver) works with
      individual "[N]" strings that map to single Reference entries.
      Leaving "[1,2]" unexpanded would break the ref_id lookup.
    """
    raw_matches = NUMBERED_CITATION.findall(sentence)
    markers = []

    for match in raw_matches:
        # match is the content inside brackets: e.g. "1", "1,2", "1-3"
        if '-' in match:
            # Range like "1-3" → expand to all integers in range
            parts = match.split('-')
            start, end = int(parts[0]), int(parts[1])
            markers += [f"[{i}]" for i in range(start, end + 1)]

        elif ',' in match:
            # Comma-separated list like "1,2,3" → expand each
            markers += [f"[{n.strip()}]" for n in match.split(',')]

        else:
            # Single number like "1" → simple wrap
            markers.append(f"[{match}]")

    # Deduplicate while preserving order
    # (important: [1,1] should not produce ["[1]", "[1]"])
    seen = set()
    unique = []
    for m in markers:
        if m not in seen:
            seen.add(m)
            unique.append(m)

    return unique


def split_body_and_references(full_text: str) -> tuple[str, str]:
    """
    Splits the full extracted PDF text into:
      - body_text: everything before the References section
      - ref_text: the References section and everything after

    WHY USE THE LAST MATCH:
      The word "References" can appear inside sentences in the body
      (e.g., "Smith et al. [3] references prior work on...").
      Using the LAST occurrence of a standalone "References" heading
      dramatically reduces false splits.

    Returns: (body_text, references_text)
    If no references section is found, returns (full_text, "") — the whole
    document is treated as body, with an empty bibliography.
    """
    matches = list(REFERENCES_SECTION.finditer(full_text))

    if not matches:
        # Common for papers with non-standard reference section names
        return full_text, ""

    # Take the LAST match — safest heuristic for finding the actual bibliography
    last_match = matches[-1]
    split_point = last_match.start()

    body_text = full_text[:split_point]
    ref_text = full_text[split_point:]

    return body_text, ref_text


def parse_bibliography(ref_text: str) -> list[Reference]:
    """
    Parses the references section text into a list of Reference objects.

    Expects numbered bibliography entries in the form:
      [1] Vaswani et al. Attention is all you need. NeurIPS 2017.
      [2] Gehring et al. Convolutional Sequence to Sequence Learning. 2017.

    WHY REGEX OVER LINE-BY-LINE:
      Bibliography entries are often multi-line (long titles, many authors).
      The DOTALL regex handles this naturally by including newlines in the match.
      We flatten each match to a single line when creating the Reference.

    Returns: list of Reference(ref_id="[1]", raw_text="Vaswani et al...")
    """
    references = []

    for match in BIBLIOGRAPHY_ENTRY.finditer(ref_text):
        ref_id = match.group(1).strip()    # e.g. "[1]"
        raw = match.group(2).strip()       # everything after [N]
        raw = raw.replace('\n', ' ')       # flatten multi-line entries to one line

        references.append(Reference(
            ref_id=ref_id,
            raw_text=raw,
            citation_style="numbered"
        ))

    return references


def extract_citation_sentences(body_text: str) -> list[dict]:
    """
    Scans the body text sentence by sentence and returns ONLY those sentences
    that contain at least one citation marker like [1], [2], [1,2], etc.

    WHY FILTER:
      Papers have hundreds of sentences, but only a fraction cite sources.
      By filtering to citation sentences first, we massively reduce the number
      of LLM tokens needed (and cost) in the claim extraction step.

    Each returned item is a dict:
    {
        "sentence": "full sentence text with markers",
        "citations": ["[1]", "[3]"],    ← pre-expanded markers
        "sentence_index": 42            ← position in the full sentence list
    }

    WHY KEEP sentence_index:
      Used by claim_extractor to map claims back to their section
      (section_lookup is built from sentence_index ranges).
    """
    # Split on sentence-ending punctuation followed by whitespace
    # (?<=[.!?]) is a lookbehind — keeps the punctuation in the previous sentence
    sentences = re.split(r'(?<=[.!?])\s+', body_text)

    result = []
    for index, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue

        markers = find_citation_markers(sentence)
        
        # Author-year style: (Vaswani et al., 2017) or (Smith, 2020)
        author_year = re.findall(
            r'\([A-Z][a-z]+(?:\s+et al\.?)?,?\s+\d{4}\)', sentence
        )
        
        # Keyword-based claims: "We show", "Results demonstrate", etc.
        claim_keywords = [
            "we show", "we propose", "we demonstrate", "we present",
            "results show", "experiments show", "our method", "our approach",
            "outperforms", "achieves state-of-the-art", "improves over",
            "we find that", "we conclude", "we introduce",
            "results demonstrate", "our model", "significantly better"
        ]
        has_keyword = any(kw in sentence.lower() for kw in claim_keywords)
        
        all_markers = markers + author_year

        # Include if: [1] style OR (Author, year) style OR keyword claim
        if all_markers or has_keyword:
            result.append({
                "sentence": sentence,
                "citations": all_markers if all_markers else ["keyword-claim"],
                "sentence_index": index
            })

    return result


def find_section_boundaries(body_text: str) -> list[dict]:
    """
    Detects section headings in the paper body using two complementary strategies:

    STRATEGY 1 — Known heading names:
      Searches for standard academic section words (Introduction, Methods, etc.)
      using the SECTION_HEADING regex. High precision, lower recall.

    STRATEGY 2 — Short standalone lines:
      Any line that is:
        - short (< 60 chars)
        - doesn't end with '.' (not a regular sentence)
        - non-empty (> 3 chars)
        - has no citation markers
      ...is treated as a likely heading. Higher recall, lower precision.

    Both strategies contribute to the same `found` dict, deduplicating by
    character position. Results are sorted by position and given section IDs.

    Returns:
    [
        {"heading": "Introduction", "start_char": 120, "section_id": "s1"},
        {"heading": "Related Work", "start_char": 890, "section_id": "s2"},
        ...
    ]
    """
    found = {}  # Dict keyed by start_char to avoid duplicates from both strategies

    # Strategy 1: match known academic section names
    for match in SECTION_HEADING.finditer(body_text):
        start = match.start()
        heading = match.group(0).strip()
        found[start] = heading

    # Strategy 2: short standalone lines as candidate headings
    lines = body_text.split('\n')
    char_pos = 0
    for line in lines:
        stripped = line.strip()

        is_short = len(stripped) < 60        # headings are brief
        is_not_sentence = not stripped.endswith('.')   # sentences end with period
        is_not_empty = len(stripped) > 3
        has_no_citation = not NUMBERED_CITATION.search(stripped)  # avoid "[3] Smith et al."

        if is_short and is_not_sentence and is_not_empty and has_no_citation:
            # Only add if Strategy 1 didn't already claim this position
            if char_pos not in found:
                found[char_pos] = stripped

        char_pos += len(line) + 1  # +1 accounts for the '\n' we split on

    # Sort all found headings by their character position (document order)
    sorted_sections = sorted(found.items(), key=lambda x: x[0])

    # Assign sequential section IDs: s1, s2, s3...
    sections = []
    for i, (start_char, heading) in enumerate(sorted_sections):
        sections.append({
            "heading": heading,
            "start_char": start_char,
            "section_id": f"s{i + 1}"
        })

    return sections