from fastapi import APIRouter, UploadFile, File
import os
import shutil

# Services
from backend.services.citation_checker import check_sources
from backend.services.paper_fetcher import fetch_with_fallback
from backend.services.claim_verifier import verify_all_claims

from backend.services.pdf_parser import (
    extract_full_text,
    extract_references,
    extract_claims_with_citations,
    map_claims_to_references
)

router = APIRouter()

UPLOAD_DIR = "backend/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# 🔥 helper: shorten text for better search
def get_short_query(text, max_words=10):
    words = text.split()
    return " ".join(words[:max_words])


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        return {"error": "Only PDF allowed"}

    # ✅ STEP 1: Save file
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # ✅ STEP 2: Parse PDF
    text = extract_full_text(file_path)
    references = extract_references(text)
    claims = extract_claims_with_citations(text)
    mapped_data = map_claims_to_references(claims, references)

    # ✅ STEP 3: Source existence check
    checked_sources = check_sources(mapped_data[:5])

    # ✅ STEP 4: Fetch REAL abstracts (FIXED LOGIC)
    verification_input = []

    for item in checked_sources:
        if not item["exists"]:
            continue

        # 🔥 STEP 4A: Shorten reference
        short_ref = get_short_query(item["reference"])
        print("\n🔎 Trying reference query:", short_ref)

        abstract = fetch_with_fallback(short_ref)

        # 🔥 STEP 4B: Fallback → shortened claim
        if not abstract:
            short_claim = get_short_query(item["claim"], 12)
            print("🔁 Fallback using claim:", short_claim)
            abstract = fetch_paper_abstract(short_claim)

        # 🔥 STEP 4C: Accept only GOOD abstracts
        if abstract and len(abstract) > 50:
            print("✅ Abstract accepted\n")

            verification_input.append({
                "claim": item["claim"],
                "reference": item["reference"],
                "abstract": abstract
            })
        else:
            print("❌ No usable abstract found\n")

    print("\n--- VERIFICATION INPUT ---\n")
    print(verification_input)

    # ❗ If nothing valid found
    if not verification_input:
        return {
            "preview_text": text[:500],
            "total_claims_found": len(claims),
            "mapped_claims": mapped_data[:5],
            "source_check": checked_sources,
            "verification": [],
            "message": "No valid abstracts found (query too noisy)"
        }

    # ✅ STEP 5: Gemini verification
    verification_output = verify_all_claims(verification_input)

    # ✅ FINAL RESPONSE
    return {
        "preview_text": text[:500],
        "total_claims_found": len(claims),
        "mapped_claims": mapped_data[:5],
        "source_check": checked_sources,
        "verification_input": verification_input,  # debug
        "verification": verification_output
    }
