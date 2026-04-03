def generate_roadmap(data):
    roadmap = []

    for item in data:
        if item["score"] >= 75:
            roadmap.append({
                "topic": item["claim"][:50],
                "trust_score": item["score"]
            })

    return roadmap