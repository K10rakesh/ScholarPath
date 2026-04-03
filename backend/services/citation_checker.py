import requests
import re

SEMANTIC_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
CROSSREF_URL = "https://api.crossref.org/works"
ARXIV_URL = "http://export.arxiv.org/api/query"


# 🔧 Clean reference text before querying
def clean_query(ref: str):
    ref = re.sub(r"\[\d+\]", "", ref)  # remove [1], [2]
    ref = re.sub(r"\s+", " ", ref)     # normalize spaces
    return ref.strip()


def check_semantic_scholar(query):
    try:
        res = requests.get(
            SEMANTIC_URL,
            params={
                "query": query,
                "limit": 1,
                "fields": "title"
            },
            timeout=5
        )
        data = res.json()
        return len(data.get("data", [])) > 0
    except Exception as e:
        print("Semantic Scholar error:", e)
        return False


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
        return len(data.get("message", {}).get("items", [])) > 0
    except Exception as e:
        print("CrossRef error:", e)
        return False


def check_arxiv(query):
    try:
        res = requests.get(
            ARXIV_URL,
            params={
                "search_query": query,
                "max_results": 1
            },
            timeout=5
        )
        return "entry" in res.text.lower()
    except Exception as e:
        print("arXiv error:", e)
        return False


def check_source_exists(reference):
    query = clean_query(reference)

    print("\n🔍 Checking reference:")
    print("RAW:", reference)
    print("CLEANED:", query)

    # 1️⃣ Semantic Scholar
    if check_semantic_scholar(query):
        print("✅ Found in Semantic Scholar")
        return True

    # 2️⃣ CrossRef
    if check_crossref(query):
        print("✅ Found in CrossRef")
        return True

    # 3️⃣ arXiv
    if check_arxiv(query):
        print("✅ Found in arXiv")
        return True

    print("❌ Not found anywhere")
    return False


def check_sources(mapped_claims):
    results = []

    for item in mapped_claims:
        exists = check_source_exists(item["reference"])

        results.append({
            "claim": item["claim"],
            "citation": item["citation"],
            "reference": item["reference"],
            "exists": exists
        })

    return results
