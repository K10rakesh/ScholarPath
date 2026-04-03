import fitz
import re


# ✅ STEP 1: Extract full text
def extract_full_text(pdf_path: str):
    doc = fitz.open(pdf_path)
    text = ""

    for page in doc:
        text += page.get_text()

    return text


# ✅ STEP 2: Extract references (CORRECT INDEXING)
def extract_references(text: str):
    """
    Extract references and map actual numbers → reference text
    """

    ref_match = re.search(r"(references|bibliography)", text, re.IGNORECASE)

    if not ref_match:
        return {}

    ref_text = text[ref_match.end():]

    # 🔥 Match patterns like:
    # [1] ...
    # 1. ...
    matches = list(re.finditer(r"(?:\[(\d+)\]|^\s*(\d+)\.)", ref_text, re.MULTILINE))

    references = {}

    for i in range(len(matches)):
        match = matches[i]
        num = match.group(1) or match.group(2)
        
        start_idx = match.end()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(ref_text)
        
        content = ref_text[start_idx:end_idx].strip()
        content = re.sub(r'\s+', ' ', content)
        
        if content:
            references[num] = content

    return references


# ✅ STEP 3: Extract claims with citations
def extract_claims_with_citations(text: str):
    """
    Extract sentences containing citations
    """

    sentences = re.split(r'(?<=[.!?])\s+', text)

    claims = []

    for sentence in sentences:
        numeric_citations = re.findall(r"\[(\d+)\]", sentence)

        author_citations = re.findall(r"\(([^)]+, \d{4})\)", sentence)

        if numeric_citations or author_citations:
            claims.append({
                "claim": sentence.strip(),
                "numeric_citations": numeric_citations,
                "author_citations": author_citations
            })

    return claims


# ✅ STEP 4: CORRECT MAPPING
def map_claims_to_references(claims, references):
    """
    Map claim citations → correct references
    """

    mapped = []

    for c in claims:
        for cit in c["numeric_citations"]:
            ref = references.get(cit)

            mapped.append({
                "claim": c["claim"],
                "citation": cit,
                "reference": ref if ref else "Reference not found"
            })

    return mapped
