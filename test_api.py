import requests

def search_semantic(query):
    print(f"\nSearching: {query}")
    res = requests.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": query,
            "limit": 1,
            "fields": "title,abstract,year,authors,externalIds"
        },
        timeout=5
    )
    if res.status_code == 200:
        data = res.json()
        papers = data.get("data", [])
        if papers:
            p = papers[0]
            print(f"✅ Found: {p.get('title')}")
            print(f"Abstract length: {len(p.get('abstract') or '')}")
        else:
            print("❌ No paper found.")
    else:
        print(f"❌ HTTP Error {res.status_code}: {res.text}")

def search_crossref(query):
    print(f"\nCrossRef Searching: {query}")
    res = requests.get(
        "https://api.crossref.org/works",
        params={"query": query, "rows": 1},
        timeout=5
    )
    if res.status_code == 200:
        data = res.json()
        items = data.get("message", {}).get("items", [])
        if items:
            p = items[0]
            print(f"✅ Found DOI: {p.get('DOI')} Title: {p.get('title')}")
            return p.get("DOI")
    print("❌ No paper found in CrossRef.")
    return None

def fetch_by_doi(doi):
    print(f"\nFetching by DOI: {doi}")
    res = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}",
        params={"fields": "title,abstract,year,authors"}
    )
    if res.status_code == 200:
        p = res.json()
        print(f"✅ Found: {p.get('title')}")
        print(f"Abstract length: {len(p.get('abstract') or '')}")
    else:
        print(f"❌ HTTP Error {res.status_code}: {res.text}")

refs = [
    "Richard Van Noorden. 2016. Social-sciences preprint server snapped up by publishing giant Elsevier. Nature (May 2016).",
    "Rob Johnson and Andrea Chiarelli. 2019. The Second Wave of Preprint Servers: How Can Publishers Keep Afloat? The scholarly kitchen",
    "Arnab Sinha, Zhihong Shen, Yang Song, Hao Ma, Darrin Eide, Bo-June (Paul) Hsu, and Kuangsan Wang. 2015. An Overview of Microsoft Academic Service"
]

for ref in refs:
    # Try Semantic with original 10 words
    search_semantic(" ".join(ref.split()[:10]))
    # Try Semantic with 15 words
    search_semantic(" ".join(ref.split()[:15]))
    # Try Semantic with full ref
    search_semantic(ref)
    
    # Try CrossRef -> DOI -> Semantic
    doi = search_crossref(ref)
    if doi:
        fetch_by_doi(doi)

