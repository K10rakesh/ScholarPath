import requests
import json

def fetch_crossref(query):
    print(f"\nSearching CrossRef: {query}")
    res = requests.get(
        "https://api.crossref.org/works",
        params={"query": query, "rows": 1},
        timeout=5
    )
    if res.status_code == 200:
        data = res.json()
        items = data.get("message", {}).get("items", [])
        if items:
            return items[0]
    return None

ref = "Richard Van Noorden. 2016. Social-sciences preprint server snapped up by publishing giant Elsevier. Nature (May 2016)."
paper = fetch_crossref(ref)
if paper:
    print(json.dumps(paper, indent=2))
