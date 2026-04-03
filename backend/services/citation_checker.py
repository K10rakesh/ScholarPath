import requests
import re

CROSSREF_URL = "https://api.crossref.org/works"

# 🔧 Clean reference text before querying
def clean_query(ref: str):
    ref = re.sub(r"\[\d+\]", "", ref)  # remove [1], [2]
    ref = re.sub(r"\s+", " ", ref)     # normalize spaces
    return ref.strip()


def check_crossref(query):
    try:
        res = requests.get(
            CROSSREF_URL,
            params={
                "query": query,
                "rows": 1
            },
            timeout=5
        )
        data = res.json()
        items = data.get("message", {}).get("items", [])
        if items:
            return items[0]  # Return the ENTIRE metadata object
        return None
    except Exception as e:
        print("CrossRef error:", e)
        return None


def check_source_exists(reference):
    query = clean_query(reference)

    print("\n🔍 Checking reference:")
    print("RAW:", reference)
    print("CLEANED:", query)

    metadata = check_crossref(query)
    if metadata:
        print("✅ Found in CrossRef")
        return metadata

    print("❌ Not found anywhere")
    return None


def check_sources(mapped_claims):
    results = []

    for item in mapped_claims:
        metadata = check_source_exists(item["reference"])

        results.append({
            "claim": item["claim"],
            "citation": item["citation"],
            "reference": item["reference"],
            "exists": bool(metadata),
            "metadata": metadata
        })

    return results
