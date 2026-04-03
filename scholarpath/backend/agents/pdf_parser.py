# =============================================================================
# backend/agents/pdf_parser.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   Phase 1 of the pipeline: takes a raw PDF file path and produces a fully
#   structured ParsedPaper object (Contract 01). It handles everything from
#   opening the PDF to splitting the bibliography, detecting section headings,
#   and extracting paper metadata — then hands off to claim_extractor.py
#   (Phase 2) for the LLM-based claim identification step.
#
#   Never raises exceptions to the caller — all errors are caught, logged,
#   and stored in ParsedPaper.errors[], making the API always return a 200.
#
# CONNECTED TO:
#   ← backend/main.py                       (calls parse_pdf())
#   → backend/schemas.py                    (produces ParsedPaper, Section, Reference)
#   → backend/utils/citation_patterns.py    (all regex helpers)
#   → backend/agents/claim_extractor.py     (called in step G to get claims[])
# =============================================================================

import fitz  # PyMuPDF — installed as 'pymupdf' but imported as 'fitz'
import re

from backend.schemas import ParsedPaper, Section, Reference
from backend.utils.citation_patterns import (
    split_body_and_references,   # splits full text into body + bibliography
    parse_bibliography,           # converts bibliography lines → Reference[]
    extract_citation_sentences,   # finds sentences containing [N] markers
    find_section_boundaries       # detects section headings
)


def parse_pdf(file_path: str, doc_id: str) -> ParsedPaper:
    """
    MASTER FUNCTION — entry point for all PDF processing.

    Takes a PDF file path + doc_id string.
    Returns a ParsedPaper (Contract 01) — never raises, always returns something.

    The pipeline inside has 9 sequential steps (A through I):
      A. Open PDF → extract raw text page by page
      B. Split body text from bibliography section
      C. Parse bibliography lines into Reference objects
      D. Detect section headings → build Section objects
      E. Extract title, authors, abstract from header area
      F. Find sentences containing citation markers [N]
      G. Run LLM claim extractor on those sentences → Claim[]
      H. Assemble the final ParsedPaper object
      I. Validate citation integrity (every claim's cite must exist in references[])
    """
    try:
        # ── A: Open PDF and extract raw text ──────────────────────────────────
        doc = fitz.open(file_path)
        full_text = ""

        for page in doc:
            try:
                # sort=True ensures text is extracted in reading order (top→bottom)
                full_text += page.get_text("text", sort=True)
            except Exception as page_err:
                # Skip pages with encoding issues — don't crash the entire parse
                print(f"[pdf_parser] Warning: Could not extract text from page: {page_err}")
                continue

        if not full_text.strip():
            # PDF opened but had no extractable text — it's a scanned image PDF
            # Return a graceful "failed" result rather than crashing
            return ParsedPaper(
                doc_id=doc_id,
                file_name=file_path.split("/")[-1],
                title="Unknown",
                authors=[],
                full_text="",
                sections=[],
                references=[],
                claims=[],
                stats={},
                processing_status="failed",
                errors=[{
                    "code": "NO_TEXT_EXTRACTED",
                    "message": "PDF appears to be scanned or image-only. "
                               "Text extraction returned empty string."
                }]
            )

        # ── B: Split body text from references section ────────────────────────
        # Uses the last occurrence of "References" heading to avoid
        # splitting on "see references [1]" in the middle of the paper.
        body_text, ref_text = split_body_and_references(full_text)

        # ── C: Parse bibliography from references section ─────────────────────
        # Regex matches [N] entries and extracts each as a Reference object
        bibliography: list[Reference] = parse_bibliography(ref_text)

        # ── D: Detect and extract sections from body ──────────────────────────
        # Finds known headings (Introduction, Methods, etc.) and short standalone lines
        section_boundaries = find_section_boundaries(body_text)
        sections: list[Section] = build_sections(body_text, section_boundaries)

        # ── E: Extract paper metadata (title, authors, abstract) ──────────────
        # Heuristic-based: looks in first 30 lines for title, first 800 chars for authors
        title, authors, abstract = extract_metadata(full_text, doc)

        # ── F: Find sentences that contain citation markers ───────────────────
        # These are the raw inputs for the LLM — only sentences with [N] references
        # are worth checking for verifiable claims
        citation_sentences = extract_citation_sentences(body_text)

        # ── G: Run LLM claim extractor ────────────────────────────────────────
        # Import here (not at top) to avoid circular imports since pdf_parser
        # and claim_extractor import each other's types
        from backend.agents.claim_extractor import extract_claims
        claims = extract_claims(citation_sentences, sections)

        # ── H: Assemble the ParsedPaper contract ──────────────────────────────
        paper = ParsedPaper(
            doc_id=doc_id,
            file_name=file_path.split("/")[-1],
            title=title,
            authors=authors,
            abstract=abstract,
            full_text=full_text,
            sections=sections,
            references=bibliography,
            claims=claims,
            stats={
                "num_sections": len(sections),
                "num_references": len(bibliography),
                "num_claims": len(claims),
                "num_citation_sentences": len(citation_sentences)
            }
        )

        # ── I: Validate the foreign key constraint before returning ───────────
        # Every citation in claims[] must match a ref_id in references[].
        # If not, Member 2's citation resolver will silently fail.
        violations = paper.validate_citation_integrity()
        if violations:
            # Don't crash — mark as "partial" and log each violation
            paper.processing_status = "partial"
            for v in violations:
                paper.errors.append({
                    "code": "CITATION_INTEGRITY_VIOLATION",
                    "message": v
                })

        return paper

    except fitz.FileDataError as e:
        # PyMuPDF couldn't open the file at all — corrupted PDF
        return _error_paper(doc_id, file_path, "PDF_CORRUPT", str(e))

    except Exception as e:
        # Catch-all safety net — log and return failed paper, never expose traceback to API
        return _error_paper(doc_id, file_path, "PDF_PARSE_ERROR", str(e))


# ─── Helper: build Section objects from boundary positions ────────────────────

def build_sections(body_text: str, boundaries: list[dict]) -> list[Section]:
    """
    Given section start positions (from find_section_boundaries), slices
    body_text into Section objects.

    WHY CHARACTER SLICING:
      We have character offsets from the regex, so slicing is O(1) and
      preserves the exact text without re-splitting on newlines.

    Each section's text runs from its start_char to the next section's start_char.
    The last section runs to the end of body_text.
    """
    sections = []

    for i, boundary in enumerate(boundaries):
        start = boundary["start_char"]

        # End is the start of the next section, or end-of-text for the last one
        if i + 1 < len(boundaries):
            end = boundaries[i + 1]["start_char"]
        else:
            end = len(body_text)

        section_text = body_text[start:end].strip()

        sections.append(Section(
            section_id=boundary["section_id"],
            heading=boundary["heading"],
            text=section_text
        ))

    # Edge case: if no section headings were found at all,
    # treat the entire body as one unnamed section so downstream code
    # always has at least one Section to work with
    if not sections:
        sections.append(Section(
            section_id="s1",
            heading="Body",
            text=body_text.strip()
        ))

    return sections


# ─── Helper: extract title, authors, abstract ─────────────────────────────────

def extract_metadata(full_text: str, doc) -> tuple[str, list[str], str | None]:
    """
    Wrapper that calls the three individual metadata extractors and returns
    a tuple of (title, authors, abstract).
    The `doc` arg (PyMuPDF Document) is passed through for potential future
    use of PDF metadata fields (not currently used).
    """
    title = extract_title(full_text)
    authors = extract_authors(full_text, title)
    abstract = extract_abstract(full_text)
    return title, authors, abstract


def extract_title(full_text: str) -> str:
    """
    Heuristic title extractor. Looks at the first 30 lines of the document
    and returns the first 'substantial' line that doesn't look like a date,
    URL, page number, or very short snippet.

    WHY HEURISTICS:
      PDF metadata fields are often empty or wrong. The first non-trivial
      line in academic papers is almost always the title.
    """
    lines = full_text.split('\n')

    for line in lines[:30]:   # Title is in first 30 lines of any academic paper
        line = line.strip()

        # Filters — skip lines that are obviously not the title
        too_short = len(line) < 15
        looks_like_url = 'http' in line.lower()
        looks_like_date = bool(re.search(r'\d{4}', line) and len(line) < 25)
        looks_like_page = bool(re.match(r'^\d+$', line))

        if too_short or looks_like_url or looks_like_date or looks_like_page:
            continue

        return line  # First line that passes all filters = title

    return "Unknown Title"  # Fallback if nothing found


def extract_authors(full_text: str, title: str) -> list[str]:
    """
    Heuristic author extractor. Looks in the first 800 characters after the title
    for lines that look like author lists (short, with commas or 'and', no years).

    Intentionally simple — returns empty list rather than guessing wrong.
    Accuracy is not critical: title matters more for downstream citation lookup.
    """
    header_area = full_text[:800]  # Authors always appear near the top

    # Skip the title itself when searching for authors
    start = header_area.find(title)
    if start != -1:
        header_area = header_area[start + len(title):]

    authors = []
    lines = header_area.split('\n')

    for line in lines[:15]:
        line = line.strip()

        # Author line signatures: short, has commas or "and", no 4-digit years
        has_comma_or_and = ',' in line or ' and ' in line.lower()
        reasonable_length = 10 < len(line) < 200
        no_numbers = not bool(re.search(r'\d{4}', line))

        if has_comma_or_and and reasonable_length and no_numbers:
            # Split on "," and "and" to get individual names
            parts = re.split(r',|\band\b', line, flags=re.IGNORECASE)
            for part in parts:
                name = part.strip()
                # A real name should have 2+ words and be < 40 chars
                if name and len(name) < 40 and len(name.split()) >= 2:
                    authors.append(name)

            if authors:
                break  # Found the author line — stop looking

    return authors


def extract_abstract(full_text: str) -> str | None:
    """
    Finds the Abstract by looking for the word 'Abstract' as a heading.
    Takes the paragraph immediately following it, trimmed to 1000 chars.

    WHY 1000 CHARS:
      Abstract is used downstream as evidence text for claim verification.
      Keeping it short prevents LLM token overflow.
    """
    # Look for "Abstract" as a standalone word (standalone heading)
    match = re.search(r'\bAbstract\b', full_text, re.IGNORECASE)

    if not match:
        return None

    # Take text starting after the word "Abstract"
    after_abstract = full_text[match.end():].strip()

    # Abstract ends at first double newline (paragraph break) or 1000 chars
    paragraph_end = after_abstract.find('\n\n')
    if paragraph_end == -1 or paragraph_end > 1000:
        paragraph_end = 1000

    abstract = after_abstract[:paragraph_end].strip()
    abstract = abstract.replace('\n', ' ')   # flatten to single line for LLM input

    return abstract if len(abstract) > 50 else None  # reject tiny "abstracts"


# ─── Helper: build a failed ParsedPaper for error cases ──────────────────────

def _error_paper(doc_id: str, file_path: str, code: str, message: str) -> ParsedPaper:
    """
    Creates a minimal ParsedPaper with processing_status="failed".
    Used in exception handlers so the API always returns a structured response
    instead of crashing or returning an empty body.

    WHY ASCII SANITIZE:
      Error messages from OS or LLM can contain non-ASCII characters that
      break JSON serialisation. We strip them to stay safe.
    """
    # Sanitize message to avoid encoding issues in JSON serialisation
    safe_message = message.encode('ascii', 'replace').decode('ascii')[:200]
    return ParsedPaper(
        doc_id=doc_id,
        # Handle both Windows (\) and Unix (/) path separators
        file_name=file_path.split("\\")[-1].split("/")[-1],
        title="Unknown",
        authors=[],
        full_text="",
        sections=[],
        references=[],
        claims=[],
        stats={},
        processing_status="failed",
        errors=[{"code": code, "message": safe_message}]
    )