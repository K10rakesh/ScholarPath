from groq import Groq
import os
import re
from dotenv import load_dotenv

# ✅ Load environment variables
load_dotenv()

# ✅ Get Groq API key (assumes you will add GROQ_API_KEY to .env)
API_KEY = os.getenv("GROQ_API_KEY")
print("GROQ API KEY LOADED:", "YES" if API_KEY else "NO")

# ✅ Configure Groq
client = Groq(api_key=API_KEY)


def extract_score(text):
    numbers = re.findall(r"\d+", text)
    return int(numbers[-1]) if numbers else 0

def extract_topic(text):
    match = re.search(r"Topic:\s*(.*)", text, re.IGNORECASE)
    return match.group(1).strip() if match else "None"

import json

def verify_claim_with_gemini(claim, metadata):
    try:
        # Extract only the essential parts of the metadata to prevent Groq token limits/errors
        # and truncate massive abstracts to a safe length (e.g. 2000 chars)
        title_list = metadata.get("title", [])
        title = title_list[0] if title_list else "Unknown Title"
        abstract = metadata.get("abstract", "")[:2000]

        clean_metadata = {
            "title": title,
            "abstract": abstract
        }

        metadata_str = json.dumps(clean_metadata, indent=2)
        prompt = f"""
        Analyze the following claim and the publication metadata of the cited reference.

        Claim:
        {claim}

        Reference Metadata (JSON):
        {metadata_str}

        Task 1: If the similarity score (how well the source supports the claim) is greater than 0, summarize the claim into a short, concise topic (2-5 words). Otherwise, just return "None".
        Task 2: Based on the title, authors, venue, abstract, give a similarity score from 0 to 100 representing how well the source supports the claim.

        Format your output exactly like this:
        Topic: <topic summary or None>
        Score: <number>
        """

        response = client.chat.completions.create(
            model="openai/gpt-oss-20b", # Free and extremely fast Groq model
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )

        # ✅ Safe extraction
        output = response.choices[0].message.content
        if not output:
            print("Empty Groq response")
            return {"score": 0, "topic": "None"}

        output = output.strip()

        print("Groq raw output:", output)

        score = extract_score(output)
        topic = extract_topic(output)

        return {"score": score, "topic": topic}

    except Exception as e:
        print("Groq error:", e)
        return {"score": 0, "topic": "None"}


import time

def verify_all_claims(data):
    results = []

    for item in data:
        verification_result = verify_claim_with_gemini(
            item["claim"],
            item["metadata"]
        )
        score = verification_result["score"]
        topic = verification_result["topic"]

        # Assign color based on score
        if score <= 50:
            color = "red"
        elif 50 < score <= 75:
            color = "yellow"
        else:
            color = "green"

        results.append({
            "claim": item["claim"],
            "reference": item["reference"],
            "score": score,
            "topic": topic,
            "color": color
        })

        # Sleep briefly to avoid hitting Groq's Free Tier Rate Limits (RPM)
        time.sleep(1)

    return results
