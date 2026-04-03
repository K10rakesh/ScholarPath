import google.generativeai as genai
import os
import re
from dotenv import load_dotenv

# ✅ Load environment variables
load_dotenv()

# ✅ Get API key
API_KEY = os.getenv("GOOGLE_API_KEY")
print("GOOGLE API KEY LOADED:", "YES" if API_KEY else "NO")

# ✅ Configure Gemini
genai.configure(api_key=API_KEY)

# ✅ USE CORRECT MODEL (from your available list)
model = genai.GenerativeModel("models/gemini-2.5-flash")


def extract_score(text):
    numbers = re.findall(r"\d+", text)
    return int(numbers[0]) if numbers else 0


import json

def verify_claim_with_gemini(claim, metadata):
    try:
        metadata_str = json.dumps(metadata, indent=2)
        prompt = f"""
        Compare the following claim and the publication metadata of the cited reference.

        Claim:
        {claim}

        Reference Metadata (JSON):
        {metadata_str}

        Based on the title, authors, venue, abstract (if present), and other metadata, give a similarity score from 0 to 100 representing how well the source metadata corresponds to or supports the claim.

        Return ONLY a number.
        """

        response = model.generate_content(prompt)

        # ✅ Safe extraction
        if not response or not response.text:
            print("Empty Gemini response")
            return 0

        output = response.text.strip()

        print("Gemini raw output:", output)

        score = extract_score(output)

        return score

    except Exception as e:
        print("Gemini error:", e)
        return 0


def verify_all_claims(data):
    results = []

    for item in data:
        score = verify_claim_with_gemini(
            item["claim"],
            item["metadata"]
        )

        results.append({
            "claim": item["claim"],
            "reference": item["reference"],
            "score": score
        })

    return results
