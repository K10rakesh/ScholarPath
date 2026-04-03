from crewai import Task
from backend.crew.agents import verification_agent, roadmap_agent

def create_verification_task(data):
    return Task(
        description=f"""
        For each item below:

        {data}

        Compare the claim with the abstract.

        Output STRICT JSON list:
        [
          {{
            "claim": "...",
            "score": 0-100
          }}
        ]

        Score meaning:
        0 = unrelated
        100 = fully supported
        """,
        agent=verification_agent
    )

def create_roadmap_task(verified_claims):
    return Task(
        description=f"""
        The following topics have been extracted and verified from academic papers:
        {verified_claims}

        Your task is to generate a comprehensive learning roadmap to learn about these topics.
        Return ONLY a STRICT JSON array of objects representing study topics.
        Example format:
        [
            {{"step": 1, "topic": "Introduction to Machine Learning", "description": "Learn the basics..."}},
            {{"step": 2, "topic": "Advanced Analytics", "description": "Deep dive into features..."}}
        ]
        Limit your structural roadmap to 3 to 5 steps mapping logically from start to complex.
        """,
        agent=roadmap_agent,
        expected_output="A JSON array of roadmap steps."
    )
