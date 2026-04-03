from crewai import Crew
from backend.crew.tasks import create_verification_task

def run_verification_agent(data):
    task = create_verification_task(data)

    crew = Crew(
        agents=[task.agent],
        tasks=[task],
        verbose=True
    )

    result = crew.kickoff()
    return result
