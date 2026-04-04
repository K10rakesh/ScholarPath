import fitz
import re

# ✅ STEP 1: Extract full text
def extract_full_text(pdf_path: str):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# ✅ STEP 2: Extract references
def extract_references(text: str):
    ref_match = re.search(r"(references|bibliography)", text, re.IGNORECASE)    
    if not ref_match: return {}
    ref_text = text[ref_match.end():]
    matches = list(re.finditer(r"(?:\[(\d+)\]|^\s*(\d+)\.)", ref_text, re.MULTILINE))
    references = {}
    for i in range(len(matches)):
        match = matches[i]
        num = match.group(1) or match.group(2)
        start_idx = match.end()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(ref_text)
        content = ref_text[start_idx:end_idx].strip()
        content = re.sub(r'\s+', ' ', content)
        if content: references[num] = content
    return references

# ✅ STEP 3: Extract claims with diverse patterns and contextual lookback
def extract_claims_with_citations(text: str):
    # Clean text to prevent hyphenated breaks
    text = re.sub(r'-\n', '', text)
    text = re.sub(r'\n', ' ', text)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    claims = []

    for i, sentence in enumerate(sentences):
        # Match standard or comma-separated ([1], [1, 2], [1,2,3])
        numeric_raw = re.findall(r"\[([\d\s,]+)\]", sentence)
        numeric_citations = []
        for raw in numeric_raw:
            for num in raw.split(','):
                num = num.strip()
                if num.isdigit():
                    numeric_citations.append(num)

        # Match range citations ([1-3])
        range_raw = re.findall(r"\[(\d+)\s*-\s*(\d+)\]", sentence)
        for start, end in range_raw:
            try:
                start_i, end_i = int(start), int(end)
                if end_i - start_i < 10: # Prevent massive fake ranges
                    numeric_citations.extend([str(n) for n in range(start_i, end_i + 1)])
            except ValueError: pass

        # Match Author-Year citations like (Smith et al., 2020)
        author_citations = re.findall(r"\(([^)]+,\s*\d{4})\)", sentence)

        if numeric_citations or author_citations:
            # Prepend the PREVIOUS sentence to give the LLM better logical context
            context = sentences[i-1].strip() + " " if i > 0 else ""
            full_claim = context + sentence.strip()

            # Filter out trivially short or malformed claims
            if len(full_claim) > 40:
                claims.append({
                    "claim": full_claim,
                    "numeric_citations": list(set(numeric_citations)),
                    "author_citations": list(set(author_citations))
                })

    return claims

# ✅ STEP 4: CORRECT MAPPING
def map_claims_to_references(claims, references):
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
