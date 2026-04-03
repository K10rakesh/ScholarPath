# =============================================================================
# backend/agents/citation_resolver.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   The Citation Resolution Agent (Contract 02). Takes every bibliography entry
#   from the ParsedPaper (e.g., "[3] Vaswani et al. Attention is All You Need.")
#   and attempts to match it to real paper metadata by searching academic APIs.
#
#   Resolution strategy per reference (tries each in order, stops at first success):
#     1. Semantic Scholar API — best metadata (title, abstract, DOI, authors, date)
#     2. arXiv API — good for CS/ML papers, returns ATOM XML
#     3. Unresolved — if both APIs fail or return no match
#
#   Rate limiting: Semantic Scholar free tier allows ~100 requests per 5 minutes.
#   We add a 3.5s sleep between requests to stay under the limit safely.
#
# CONNECTED TO:
#   ← backend/main.py                   (calls resolve_citations())
#   → backend/schemas_member2.py        (input: ParsedPaper, output: ResolvedCitationsOutput)
# =============================================================================

import re
import hashlib
import httpx
import time
from typing import Optional
from datetime import datetime

from backend.schemas_member2 import (
    ResolvedCitation,
    ResolvedCitationsOutput,
    ResolutionStatus,
    ProcessingStatus,
    ParsedPaper,
)


# =============================================================================
# Configuration
# =============================================================================

# Semantic Scholar API endpoints
SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_RECOMMENDATIONS_URL = "https://api.semanticscholar.org/recommendations/v1/papers"

# arXiv API endpoint (use HTTPS to avoid redirect issues)
ARXIV_API_URL = "https://export.arxiv.org/api/query"

# Timeout for API requests
API_TIMEOUT = 10.0  # seconds


# =============================================================================
# Main entry point
# =============================================================================

def resolve_citations(parsed_paper: ParsedPaper) -> ResolvedCitationsOutput:
    """
    Main entry point for citation resolution.

    Args:
        parsed_paper: ParsedPaper from Member 1 (Contract 01)

    Returns:
        ResolvedCitationsOutput (Contract 02)
    """
    doc_id = parsed_paper.doc_id
    resolved = []
    errors = []

    for reference in parsed_paper.references:
        try:
            # Limit carefully to math boundary for S2 free tier (100 req per 5 minutes = 3.0s minimum)
            time.sleep(1.0)
            resolved_citation = _resolve_single_citation(reference)
            resolved.append(resolved_citation)
        except Exception as e:
            errors.append({
                "code": "RESOLUTION_ERROR",
                "message": f"Failed to resolve {reference.ref_id}: {str(e)}"
            })
            resolved.append(ResolvedCitation(
                ref_id=reference.ref_id,
                resolution_status=ResolutionStatus.UNRESOLVED,
                raw_text=reference.raw_text
            ))

    # Calculate stats
    resolved_count = sum(
        1 for r in resolved
        if r.resolution_status in (ResolutionStatus.RESOLVED, ResolutionStatus.PARTIALLY_RESOLVED)
    )

    return ResolvedCitationsOutput(
        doc_id=doc_id,
        resolved_citations=resolved,
        stats={
            "total_references": len(parsed_paper.references),
            "resolved_count": resolved_count,
            "unresolved_count": len(parsed_paper.references) - resolved_count
        },
        processing_status=ProcessingStatus.SUCCESS if not errors else ProcessingStatus.PARTIAL,
        errors=errors
    )


# =============================================================================
# Private helpers
# =============================================================================

def _resolve_single_citation(reference) -> ResolvedCitation:
    """
    Resolve a single bibliography entry to real paper metadata.

    Strategy:
    1. Try Semantic Scholar API first (best metadata coverage)
    2. Fall back to arXiv API (good for CS/ML papers)
    3. Return unresolved if both fail
    """
    raw_text = reference.raw_text
    ref_id = reference.ref_id

    # Normalize the raw text for searching
    normalized = _normalize_citation_text(raw_text)

    # Extract potential title from citation text
    potential_title = _extract_title_from_citation(raw_text)

    if not potential_title:
        return ResolvedCitation(
            ref_id=ref_id,
            resolution_status=ResolutionStatus.UNRESOLVED,
            raw_text=raw_text
        )

    # Try Semantic Scholar first
    result = _search_semantic_scholar(potential_title)
    if result:
        authors = [a.get("name") for a in result.get("authors", []) if isinstance(a, dict) and a.get("name")]
        return ResolvedCitation(
            ref_id=ref_id,
            resolution_status=ResolutionStatus.RESOLVED,
            matched_title=result.get("title"),
            authors=authors,
            year=_parse_year(result.get("publicationDate")),
            abstract=result.get("abstract"),
            doi=result.get("externalIds", {}).get("DOI"),
            paper_id=f"semantic_{result.get('paperId', '')}",
            source_provider="semantic_scholar",
            source_url=f"https://www.semanticscholar.org/paper/{result.get('paperId', '')}",
            confidence=_calculate_confidence(result, potential_title),
            raw_text=raw_text
        )

    # Fall back to arXiv
    result = _search_arxiv(potential_title)
    if result:
        return ResolvedCitation(
            ref_id=ref_id,
            resolution_status=ResolutionStatus.RESOLVED,
            matched_title=result.get("title"),
            authors=result.get("authors", []),
            year=_parse_year(result.get("published")),
            abstract=result.get("summary"),
            doi=None,
            paper_id=f"arxiv_{result.get('arxiv_id', '')}",
            source_provider="arxiv",
            source_url=f"https://arxiv.org/abs/{result.get('arxiv_id', '')}",
            confidence=_calculate_confidence(result, potential_title),
            raw_text=raw_text
        )

    # Could not resolve
    return ResolvedCitation(
        ref_id=ref_id,
        resolution_status=ResolutionStatus.UNRESOLVED,
        raw_text=raw_text
    )


def _normalize_citation_text(text: str) -> str:
    """Clean up citation text for better matching."""
    # Remove leading citation markers like "[1]", "[2]"
    text = re.sub(r'^\[\d+\]\s*', '', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _extract_title_from_citation(text: str) -> Optional[str]:
    """
    Extract the paper title from a bibliography entry.

    Handles common formats:
    - "Title. Authors. Venue. Year."
    - "Authors. Title. Venue. Year."
    """
    # Clean up the text
    text = _normalize_citation_text(text)

    # Pattern 1: Title at the start (ends with period before authors)
    # e.g., "Neural machine translation by jointly learning to align and translate. Bahdanau et al."
    match = re.match(r'^([A-Z][^.]+(?:\.[^A-Z][^.]+)*?)\.\s*(?:[A-Z][a-z]+|et al)', text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Pattern 2: Look for quoted title
    match = re.search(r'[""]([^""]+)[""]', text)
    if match:
        return match.group(1).strip()

    # Pattern 3: First sentence-like segment (capitalized, ends with period)
    # Skip if it looks like an author name (short, contains comma)
    match = re.match(r'^([A-Z][^.]{20,}?[^.])\.', text)
    if match:
        candidate = match.group(1).strip()
        if ',' not in candidate and len(candidate.split()) > 2:
            return candidate

    # Fallback: use the first 15 words as a search query
    words = text.split()
    if len(words) >= 3:
        return ' '.join(words[:min(15, len(words))])

    return None


_SS_BACKOFF_UNTIL = 0
_ARXIV_BACKOFF_UNTIL = 0

def _search_semantic_scholar(title: str, max_retries: int = 2) -> Optional[dict]:
    """
    Search Semantic Scholar API for a paper by title.
    Returns paper metadata if found, None otherwise.
    """
    global _SS_BACKOFF_UNTIL
    if time.time() < _SS_BACKOFF_UNTIL:
        return None

    # Use exact title match first
    params = {
        "query": title[:200],  # API has length limits
        "limit": 3,
        "fields": "title,authors,publicationDate,abstract,externalIds,paperId"
    }

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=API_TIMEOUT, follow_redirects=True) as client:
                response = client.get(SEMANTIC_SCHOLAR_SEARCH_URL, params=params)
                
                if response.status_code == 429:
                    print(f"[citation_resolver] Semantic Scholar rate limit hit (429). Retrying in {2 ** attempt}s...")
                    if attempt == max_retries - 1:
                        _SS_BACKOFF_UNTIL = time.time() + 60
                    else:
                        time.sleep(2 ** attempt)
                    continue

                response.raise_for_status()
                data = response.json()

                if data.get("data"):
                    # Return the best match
                    return data["data"][0]
                
                break

        except httpx.TimeoutException:
            print("[citation_resolver] Semantic Scholar timeout")
            time.sleep(2)
        except httpx.HTTPError as e:
            print(f"[citation_resolver] Semantic Scholar HTTP error: {e}")
            break
        except Exception as e:
            print(f"[citation_resolver] Semantic Scholar error: {e}")
            break

    return None


def _search_arxiv(title: str, max_retries: int = 2) -> Optional[dict]:
    """
    Search arXiv API for a paper by title.
    Returns paper metadata if found, None otherwise.
    """
    global _ARXIV_BACKOFF_UNTIL
    if time.time() < _ARXIV_BACKOFF_UNTIL:
        return None

    # arXiv uses ATOM XML format
    params = {
        "search_query": f"ti:{title}",
        "start": 0,
        "max_results": 3
    }

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=API_TIMEOUT, follow_redirects=True) as client:
                response = client.get(ARXIV_API_URL, params=params)

                if response.status_code in (429, 503):
                    print(f"[citation_resolver] arXiv rate limit or temp error ({response.status_code}). Retrying in {2 ** attempt}s...")
                    if attempt == max_retries - 1:
                        _ARXIV_BACKOFF_UNTIL = time.time() + 60
                    else:
                        time.sleep(2 ** attempt)
                    continue

                response.raise_for_status()

                # Parse ATOM XML
                result = _parse_arxiv_response(response.text)
                if result:
                    return result
                break

        except httpx.TimeoutException:
            print("[citation_resolver] arXiv timeout")
            time.sleep(2)
        except httpx.HTTPError as e:
            print(f"[citation_resolver] arXiv HTTP error: {e}")
            break
        except Exception as e:
            print(f"[citation_resolver] arXiv error: {e}")
            break

    return None


def _parse_arxiv_response(xml_text: str) -> Optional[dict]:
    """Parse arXiv ATOM XML response."""
    import xml.etree.ElementTree as ET

    try:
        # Handle namespaces
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }

        root = ET.fromstring(xml_text)
        entries = root.findall('atom:entry', ns)

        if not entries:
            return None

        entry = entries[0]

        # Extract title
        title_elem = entry.find('atom:title', ns)
        title = title_elem.text.strip() if title_elem is not None else None

        # Extract authors
        authors = []
        for author in entry.findall('atom:author', ns):
            name_elem = author.find('atom:name', ns)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())

        # Extract summary/abstract
        summary_elem = entry.find('atom:summary', ns)
        abstract = summary_elem.text.strip() if summary_elem is not None else None

        # Extract published date
        published_elem = entry.find('atom:published', ns)
        published = published_elem.text if published_elem is not None else None

        # Extract arXiv ID
        id_elem = entry.find('atom:id', ns)
        arxiv_id = None
        if id_elem is not None and id_elem.text:
            match = re.search(r'arxiv\.org/abs/([^/\s]+)', id_elem.text)
            if match:
                arxiv_id = match.group(1)

        return {
            "title": title,
            "authors": authors,
            "summary": abstract,
            "published": published,
            "arxiv_id": arxiv_id
        }

    except Exception as e:
        print(f"[citation_resolver] arXiv XML parse error: {e}")
        return None


def _parse_year(date_str: Optional[str]) -> Optional[int]:
    """Extract year from a date string."""
    if not date_str:
        return None
    try:
        # Handle ISO format like "2017-06-12"
        match = re.match(r'(\d{4})', date_str)
        if match:
            return int(match.group(1))
    except:
        pass
    return None


def _calculate_confidence(result: dict, query_title: str) -> float:
    """
    Calculate confidence score for a match.
    Based on title similarity and data completeness.
    """
    confidence = 0.5  # base confidence for any match

    # Title similarity boost
    result_title = result.get("title", "")
    if result_title:
        similarity = _title_similarity(query_title, result_title)
        confidence += similarity * 0.4

    # Completeness boost
    if result.get("abstract"):
        confidence += 0.05
    if result.get("authors"):
        confidence += 0.03
    if result.get("publicationDate") or result.get("published"):
        confidence += 0.02

    return min(confidence, 1.0)


def _title_similarity(title1: str, title2: str) -> float:
    """
    Calculate similarity between two titles.
    Returns 1.0 for exact match, 0.0 for completely different.
    """
    # Normalize both titles
    def normalize(t):
        t = t.lower()
        t = re.sub(r'[^\w\s]', '', t)
        t = re.sub(r'\s+', ' ', t)
        return t.strip()

    n1, n2 = normalize(title1), normalize(title2)

    # Exact match
    if n1 == n2:
        return 1.0

    # One contains the other
    if n1 in n2 or n2 in n1:
        return 0.9

    # Word overlap
    words1 = set(n1.split())
    words2 = set(n2.split())

    if not words1 or not words2:
        return 0.0

    overlap = len(words1 & words2)
    total = len(words1 | words2)

    return overlap / total if total > 0 else 0.0
