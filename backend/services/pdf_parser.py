import fitz
import re

# ✅ STEP 1: Extract full text
def extract_full_text(pdf_path: str):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
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

# ✅ STEP 3: Extract claims with diverse patterns, lookback, AND HYPERLINKS
def extract_claims_with_citations(text: str, pdf_path: str = None):
    # Clean text to prevent hyphenated breaks
    text = re.sub(r'-\n', '', text)
    text = re.sub(r'\n', ' ', text)

    sentences = re.split(r'(?<=[.!?])\s+', text)
    claims = []

    for i, sentence in enumerate(sentences):
        # 1. Standard Citations
        numeric_raw = re.findall(r"\[([\d\s,]+)\]", sentence)
        numeric_citations = []
        for raw in numeric_raw:
            for num in raw.split(','):
                num = num.strip()
                if num.isdigit():
                    numeric_citations.append(num)

        range_raw = re.findall(r"\[(\d+)\s*-\s*(\d+)\]", sentence)
        for start, end in range_raw:
            try:
                start_i, end_i = int(start), int(end)
                if end_i - start_i < 10:
                    numeric_citations.extend([str(n) for n in range(start_i, end_i + 1)])
            except ValueError: pass

        author_citations = re.findall(r"\(([^)]+,\s*\d{4})\)", sentence)
        
        # 2. Direct embedded textual URLs / DOIs
        direct_urls = re.findall(r"(https?://[^\s()\]]+|doi\.org/[^\s()\]]+)", sentence)

        if numeric_citations or author_citations or direct_urls:
            context = sentences[i-1].strip() + " " if i > 0 else ""
            full_claim = context + sentence.strip()

            if len(full_claim) > 40:
                claims.append({
                    "claim": full_claim,
                    "numeric_citations": list(set(numeric_citations)),
                    "author_citations": list(set(author_citations)),
                    "direct_urls": list(set(direct_urls))
                })

    # 3. Spatial Hyperlink Extraction (bounding boxes)
    if pdf_path:
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                links = page.get_links()
                for link in links:
                    if link["kind"] == fitz.LINK_URI and link["uri"]:
                        # Extract the text under the clickable invisible rectangle
                        rect = fitz.Rect(link["from"])
                        link_text = page.get_text("text", clip=rect).strip()
                        
                        # Find which sentence contains this hyperlinked text
                        if link_text and len(link_text) > 3:
                            for i, sentence in enumerate(sentences):
                                if link_text in sentence:
                                    context = sentences[i-1].strip() + " " if i > 0 else ""
                                    full_claim = context + sentence.strip()
                                    if len(full_claim) > 40:
                                        claims.append({
                                            "claim": full_claim,
                                            "numeric_citations": [],
                                            "author_citations": [],
                                            "direct_urls": [link["uri"]]
                                        })
            doc.close()
        except Exception as e:
            print("Hyperlink extraction error:", e)

    return claims

# ✅ STEP 4: CORRECT MAPPING
def map_claims_to_references(claims, references):
    mapped = []
    
    for c in claims:
        # Add claims that have numeric references
        for cit in c.get("numeric_citations", []):
            ref = references.get(cit)
            mapped.append({
                "claim": c["claim"],
                "citation": cit,
                "reference": ref if ref else "Reference not found"
            })
            
        # Also directly append claims that have URLs! We can use the URL as the reference text
        for url in c.get("direct_urls", []):
            mapped.append({
                "claim": c["claim"],
                "citation": "Hyperlink",
                "reference": url
            })
            
    return mapped
