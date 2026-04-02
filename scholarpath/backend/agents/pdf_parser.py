# backend/agents/pdf_parser.py
# Core PDF parsing agent.
# Input:  path to a PDF file + a doc_id string
# Output: ParsedPaper object (Contract 01)

import fitz  # PyMuPDF — installed as 'pymupdf' but imported as 'fitz'
import re

from backend.schemas import ParsedPaper, Section, Reference
from backend.utils.citation_patterns import (
    split_body_and_references,
    parse_bibliography,
    extract_citation_sentences,
    find_section_boundaries
)


def parse_pdf(file_path: str, doc_id: str) -> ParsedPaper:
    """
    Master function. Takes a PDF path and returns the full ParsedPaper contract.
    Never raises — all errors are caught and stored in ParsedPaper.errors[].
    """
    try:
        # ── A: Open PDF and extract raw text ──────────────────────────────────
        doc = fitz.open(file_path)
        full_text = ""

        for page in doc:
            full_text += page.get_text()

        if not full_text.strip():
            # PDF opened but no text extracted — likely a scanned image PDF
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
        body_text, ref_text = split_body_and_references(full_text)

        # ── C: Parse bibliography from references section ─────────────────────
        bibliography: list[Reference] = parse_bibliography(ref_text)

        # ── D: Detect and extract sections from body ──────────────────────────
        section_boundaries = find_section_boundaries(body_text)
        sections: list[Section] = build_sections(body_text, section_boundaries)

        # ── E: Extract paper metadata (title, authors, abstract) ──────────────
        title, authors, abstract = extract_metadata(full_text, doc)

        # ── F: Find sentences that contain citation markers ───────────────────
        # These are the raw inputs for the LLM claim extractor in Phase 2
        citation_sentences = extract_citation_sentences(body_text)

        # ── G: Run LLM claim extractor ────────────────────────────────────────
        # Import here (not at top) to avoid circular imports
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
        violations = paper.validate_citation_integrity()
        if violations:
            # Don't crash — mark as partial and log the violations
            paper.processing_status = "partial"
            for v in violations:
                paper.errors.append({
                    "code": "CITATION_INTEGRITY_VIOLATION",
                    "message": v
                })

        return paper

    except fitz.FileDataError as e:
        # PyMuPDF couldn't read the file at all
        return _error_paper(doc_id, file_path, "PDF_CORRUPT", str(e))

    except Exception as e:
        # Catch-all — log everything, never crash the API
        return _error_paper(doc_id, file_path, "PDF_PARSE_ERROR", str(e))


# ─── Helper: build Section objects from boundary positions ────────────────────

def build_sections(body_text: str, boundaries: list[dict]) -> list[Section]:
    """
    Given section start positions, slices body_text into Section objects.
    Each section's text runs from its start_char to the next section's start_char.
    """
    sections = []

    for i, boundary in enumerate(boundaries):
        start = boundary["start_char"]

        # The section text ends where the next section begins
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

    # If no sections detected, treat the whole body as one unnamed section
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
    Heuristic metadata extraction. Not perfect but good enough for MVP.
    Returns (title, authors, abstract)
    """
    title = extract_title(full_text)
    authors = extract_authors(full_text, title)
    abstract = extract_abstract(full_text)
    return title, authors, abstract


def extract_title(full_text: str) -> str:
    """
    Title is usually the first substantial line in the document.
    Skip lines that are too short, look like dates, or look like URLs.
    """
    lines = full_text.split('\n')

    for line in lines[:30]:          # Title is almost always in first 30 lines
        line = line.strip()

        too_short = len(line) < 15
        looks_like_url = 'http' in line.lower()
        looks_like_date = bool(re.search(r'\d{4}', line) and len(line) < 25)
        looks_like_page = bool(re.match(r'^\d+$', line))

        if too_short or looks_like_url or looks_like_date or looks_like_page:
            continue

        return line

    return "Unknown Title"


def extract_authors(full_text: str, title: str) -> list[str]:
    """
    Authors usually appear in the first 500 characters after the title.
    Look for lines that contain comma-separated proper names.
    This is intentionally simple — returns [] if uncertain.
    """
    # Only look in the first chunk of the document
    header_area = full_text[:800]

    # Skip the title line itself
    start = header_area.find(title)
    if start != -1:
        header_area = header_area[start + len(title):]

    authors = []
    lines = header_area.split('\n')

    for line in lines[:15]:
        line = line.strip()

        # Author lines are usually short, have commas or "and", no verbs
        has_comma_or_and = ',' in line or ' and ' in line.lower()
        reasonable_length = 10 < len(line) < 200
        no_numbers = not bool(re.search(r'\d{4}', line))  # skip year lines

        if has_comma_or_and and reasonable_length and no_numbers:
            # Split on commas and "and" to get individual names
            parts = re.split(r',|\band\b', line, flags=re.IGNORECASE)
            for part in parts:
                name = part.strip()
                # A name should have at least 2 words and be < 40 chars
                if name and len(name) < 40 and len(name.split()) >= 2:
                    authors.append(name)

            if authors:
                break

    return authors


def extract_abstract(full_text: str) -> str | None:
    """
    Finds the abstract by looking for the word 'Abstract' as a heading.
    Takes the paragraph immediately following it.
    Trims to 1000 characters.
    """
    # Look for Abstract as a standalone word/heading
    match = re.search(r'\bAbstract\b', full_text, re.IGNORECASE)

    if not match:
        return None

    # Take text starting after the word "Abstract"
    after_abstract = full_text[match.end():].strip()

    # The abstract ends at the first double newline (paragraph break)
    # or after 1000 characters — whichever comes first
    paragraph_end = after_abstract.find('\n\n')
    if paragraph_end == -1 or paragraph_end > 1000:
        paragraph_end = 1000

    abstract = after_abstract[:paragraph_end].strip()
    abstract = abstract.replace('\n', ' ')   # flatten to single line

    return abstract if len(abstract) > 50 else None


# ─── Helper: build a failed ParsedPaper for error cases ──────────────────────

def _error_paper(doc_id: str, file_path: str, code: str, message: str) -> ParsedPaper:
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
        errors=[{"code": code, "message": message}]
    )