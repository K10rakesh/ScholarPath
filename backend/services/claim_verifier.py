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


def verify_claim_with_gemini(claim, abstract):
    try:
        prompt = f"""
        Compare the following claim and research abstract.

        Claim:
        {claim}

        Abstract:
        {abstract}

        Give a similarity score from 0 to 100.

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
            item["abstract"]
        )

        results.append({
            "claim": item["claim"],
            "reference": item["reference"],
            "score": score
        })

    return results
