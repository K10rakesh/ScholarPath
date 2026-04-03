from crewai import Task
from backend.crew.agents import verification_agent

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
