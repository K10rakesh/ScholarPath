# backend/utils/citation_patterns.py
# All regex logic for finding and parsing citation markers.
# These functions are used by both the PDF parser and claim extractor.

import re
from backend.schemas import Reference


# ─── Regex Patterns ───────────────────────────────────────────────────────────

# Matches: [1]  [12]  [1,2]  [1,2,3]  [1-3]
# Captures what's inside the brackets
NUMBERED_CITATION = re.compile(r'\[(\d+(?:[,\-]\d+)*)\]')

# Matches common section headings in academic papers
SECTION_HEADING = re.compile(
    r'^(Abstract|Introduction|Background|Related Work|'
    r'Methodology|Method|Model|Architecture|'
    r'Experiments?|Results?|Discussion|Conclusion|'
    r'Limitations?|References?|Bibliography|Appendix)',
    re.IGNORECASE | re.MULTILINE
)

# Matches a bibliography entry starting with [N]
BIBLIOGRAPHY_ENTRY = re.compile(
    r'(\[\d+\])\s+(.+?)(?=\[\d+\]|\Z)',
    re.DOTALL
)

# Matches the start of the references section
REFERENCES_SECTION = re.compile(
    r'\n\s*(References|Bibliography|Works Cited)\s*\n',
    re.IGNORECASE
)


# ─── Functions ────────────────────────────────────────────────────────────────

def find_citation_markers(sentence: str) -> list[str]:
    """
    Find all citation markers in a sentence and return them
    as a deduplicated list of "[N]" format strings.

    Handles:
      [1]     → ["[1]"]
      [1,2]   → ["[1]", "[2]"]
      [1-3]   → ["[1]", "[2]", "[3]"]
      [1,3-5] → ["[1]", "[3]", "[4]", "[5]"]
    """
    raw_matches = NUMBERED_CITATION.findall(sentence)
    markers = []

    for match in raw_matches:
        # match is what's inside the brackets e.g. "1", "1,2", "1-3"
        if '-' in match:
            # Range like "1-3" → expand to [1, 2, 3]
            parts = match.split('-')
            start, end = int(parts[0]), int(parts[1])
            markers += [f"[{i}]" for i in range(start, end + 1)]

        elif ',' in match:
            # Comma list like "1,2,3" → expand each
            markers += [f"[{n.strip()}]" for n in match.split(',')]

        else:
            # Single number like "1"
            markers.append(f"[{match}]")

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for m in markers:
        if m not in seen:
            seen.add(m)
            unique.append(m)

    return unique


def split_body_and_references(full_text: str) -> tuple[str, str]:
    """
    Splits the full PDF text into body text and references section.
    Uses the LAST match of the references heading in case the word
    'References' appears elsewhere in the paper first.

    Returns: (body_text, references_text)
    If no references section found, returns (full_text, "")
    """
    matches = list(REFERENCES_SECTION.finditer(full_text))

    if not matches:
        # No references section found — return everything as body
        return full_text, ""

    # Use the last match to avoid false positives earlier in the paper
    last_match = matches[-1]
    split_point = last_match.start()

    body_text = full_text[:split_point]
    ref_text = full_text[split_point:]

    return body_text, ref_text


def parse_bibliography(ref_text: str) -> list[Reference]:
    """
    Parses the references section into a list of Reference objects.
    Each entry must start with [N] and is a numbered citation.

    Example input:
      [1] Vaswani et al. Attention is all you need. NeurIPS 2017.
      [2] Gehring et al. Convolutional Sequence to Sequence Learning. 2017.
    """
    references = []

    for match in BIBLIOGRAPHY_ENTRY.finditer(ref_text):
        ref_id = match.group(1).strip()       # e.g. "[1]"
        raw = match.group(2).strip()          # everything after the [N]
        raw = raw.replace('\n', ' ')          # flatten multi-line entries

        references.append(Reference(
            ref_id=ref_id,
            raw_text=raw,
            citation_style="numbered"
        ))

    return references


def extract_citation_sentences(body_text: str) -> list[dict]:
    """
    Scans body text sentence by sentence.
    Returns only sentences that contain at least one citation marker.

    Each returned item is:
    {
        "sentence": "full sentence text",
        "citations": ["[1]", "[3]"],
        "sentence_index": 12
    }
    """
    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r'(?<=[.!?])\s+', body_text)

    result = []
    for index, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue

        markers = find_citation_markers(sentence)

        if markers:
            # Only keep sentences that actually have citation markers
            result.append({
                "sentence": sentence,
                "citations": markers,
                "sentence_index": index
            })

    return result


def find_section_boundaries(body_text: str) -> list[dict]:
    """
    Detects section headings in the paper body using two strategies:
    1. Common academic heading names (Introduction, Methods, etc.)
    2. Short lines (< 60 chars) that appear to be standalone headings

    Returns a list of sections ordered by position:
    [
        {"heading": "Introduction", "start_char": 120, "section_id": "s1"},
        {"heading": "Background",   "start_char": 890, "section_id": "s2"},
    ]
    """
    found = {}  # use dict keyed by start_char to avoid duplicates

    # Strategy 1: match known academic section names
    for match in SECTION_HEADING.finditer(body_text):
        start = match.start()
        heading = match.group(0).strip()
        found[start] = heading

    # Strategy 2: short standalone lines that look like headings
    lines = body_text.split('\n')
    char_pos = 0
    for line in lines:
        stripped = line.strip()
        # A heading candidate: short, not a sentence, not a number/citation
        is_short = len(stripped) < 60
        is_not_sentence = not stripped.endswith('.')
        is_not_empty = len(stripped) > 3
        has_no_citation = not NUMBERED_CITATION.search(stripped)

        if is_short and is_not_sentence and is_not_empty and has_no_citation:
            # Check it's not already found by strategy 1
            if char_pos not in found:
                found[char_pos] = stripped

        char_pos += len(line) + 1  # +1 for the \n we split on

    # Sort by position and assign section IDs
    sorted_sections = sorted(found.items(), key=lambda x: x[0])
    sections = []
    for i, (start_char, heading) in enumerate(sorted_sections):
        sections.append({
            "heading": heading,
            "start_char": start_char,
            "section_id": f"s{i + 1}"
        })

    return sections