import requests
import re

SEMANTIC_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


# 🔥 STEP 1: Clean & shorten query
def extract_search_query(text: str):
    if not text:
        return ""

    # remove URLs
    text = re.sub(r"http\S+", "", text)

    # remove citations [12]
    text = re.sub(r"\[\d+\]", "", text)

    # remove special characters
    text = re.sub(r"[^\w\s]", " ", text)

    # normalize spaces
    text = re.sub(r"\s+", " ", text)

    words = text.strip().split()

    # 🔥 Keep only first 8–10 words (CRITICAL)
    return " ".join(words[:10])

 
# 🔥 STEP 2: Fetch metadata (NOT just abstract)
def fetch_paper_metadata(reference: str, doi: str = None):
    if doi:
        print("\n🔎 Searching by DOI:", doi)
        try:
            res = requests.get(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
                params={"fields": "title,abstract,year,authors"},
                timeout=5
            )
            if res.status_code == 200:
                paper = res.json()
                abstract = paper.get("abstract")
                if abstract and len(abstract) > 50:
                    print("✅ Found paper by DOI:", paper.get("title"))
                    return {
                        "title": paper.get("title"),
                        "abstract": abstract,
                        "year": paper.get("year"),
                        "authors": [a["name"] for a in paper.get("authors", [])]
                    }
                else:
                    print("⚠️ Abstract missing/too short via DOI")
            else:
                print(f"❌ DOI Search failed: HTTP {res.status_code}")
        except Exception as e:
            print("❌ DOI Fetch error:", e)

    query = extract_search_query(reference)

    if not query or len(query) < 5:
        print("⚠️ Skipping bad query:", reference)
        return None

    print("\n🔎 Searching for:", query)

    try:
        res = requests.get(
            SEMANTIC_URL,
            params={
                "query": query,
                "limit": 1,
                "fields": "title,abstract,year,authors,url"
            },
            timeout=5
        )

        data = res.json()
        papers = data.get("data", [])

        if not papers:
            print("❌ No paper found for:", query)
            return None

        paper = papers[0]

        title = paper.get("title")
        abstract = paper.get("abstract")
        year = paper.get("year")
        authors = [a["name"] for a in paper.get("authors", [])]
        url = paper.get("url")

        print("✅ Found paper:", title)

        # 🔥 VALIDATION (very important)
        if not abstract or len(abstract) < 50:
            print("⚠️ Abstract missing/too short")
            # For roadmap, we might just want the paper even without a long abstract
            # but let's keep it to ensure quality, or create a bypass.
            pass

        return {
            "title": title,
            "abstract": abstract,
            "year": year,
            "authors": authors,
            "url": url
        }

    except Exception as e:
        print("❌ Fetch error:", e)
        return None


# 🔥 STEP 3: Optional fallback (for claims)
def fetch_with_fallback(reference: str, claim: str):
    """
    Try reference → fallback to claim
    """

    # try reference first
    metadata = fetch_paper_metadata(reference)

    if metadata:
        return metadata

    # fallback using claim (shortened)
    short_claim = " ".join(claim.split()[:12])
    print("🔁 Fallback using claim:", short_claim)

    return fetch_paper_metadata(short_claim)
