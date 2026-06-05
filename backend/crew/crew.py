# Monkey-patch CrewAI to disable cache_breakpoint for Groq
try:
    import crewai.llms.cache as _crewai_cache
    _crewai_cache.mark_cache_breakpoint = lambda msg: msg
except ImportError:
    pass

from crewai import Crew
from backend.crew.tasks import create_verification_task, create_roadmap_task
import json

def run_verification_agent(data):
    task = create_verification_task(data)

    crew = Crew(
        agents=[task.agent],
        tasks=[task],
        verbose=True
    )

    result = crew.kickoff()
    return result

def run_roadmap_agent(verified_claims):
    # Only send non-zero score topics to roadmap to reduce noise
    valid_topics = [item['topic'] for item in verified_claims if item['score'] > 0 and item.get('topic') and item['topic'] != "None"]
    
    if not valid_topics:
        return []

    task = create_roadmap_task(valid_topics)
    crew = Crew(
        agents=[task.agent],
        tasks=[task],
        verbose=True
    )

    result = crew.kickoff()
    
    # Try parsing the result text if it's formatted as stringified JSON from Crew AI
    try:
        raw_output = result.raw if hasattr(result, 'raw') else str(result)
        # Find JSON start/end if encapsulated in markdown
        import re
        match = re.search(r'\[.*\]', raw_output, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return json.loads(raw_output)
    except Exception as e:
        print("Failed to parse roadmap output as JSON", e)
        return [{"step": 1, "topic": "Unable to parse AI roadmap", "description": str(result)}]
