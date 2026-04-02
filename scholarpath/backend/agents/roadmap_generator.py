# backend/agents/roadmap_generator.py

import json
import re
import ollama

from backend.schemas import RoadmapRequest, RoadmapResponse
from backend.prompts.roadmap_generation import ROADMAP_GENERATION_PROMPT

# You can adjust this to match the team's preference
OLLAMA_MODEL = "phi3"

def generate_roadmap(request: RoadmapRequest) -> RoadmapResponse:
    """
    Main entry point for Member 3.
    Takes a RoadmapRequest contract and calls the LLM to generate the curriculum.
    Returns the strict RoadmapResponse contract.
    """
    claims_text = "\n".join([f"- {c.claim_text} ({c.verdict})" for c in request.verified_claims])
    concepts_text = ", ".join(request.key_concepts)
    
    prompt = ROADMAP_GENERATION_PROMPT.format(
        target_topic=request.target_topic,
        domain=request.domain or "General research",
        key_concepts=concepts_text,
        verified_claims=claims_text,
        max_nodes=request.constraints.get("max_nodes", 8)
    )

    # Call the LLM
    raw_response = _call_llm(prompt)
    
    # Parse and validate with Pydantic
    roadmap_data = _parse_response(raw_response)

    if roadmap_data is None:
        # Retry once on bad JSON
        print("[roadmap_generator] Parse failed, retrying...")
        retry_prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No markdown blocks."
        raw_response = _call_llm(retry_prompt)
        roadmap_data = _parse_response(raw_response)

    if roadmap_data is None:
        print("[roadmap_generator] Both attempts failed. Returning error state.")
        return RoadmapResponse(
            doc_id=request.doc_id,
            target_topic=request.target_topic,
            roadmap_summary="Failed to generate roadmap due to AI output error.",
            nodes=[],
            edges=[],
            reading_order=[],
            resource_suggestions=[],
            processing_status="failed",
            errors=[{"code": "LLM_PARSE_ERROR", "message": "Could not parse LLM output as JSON"}]
        )

    # Attach the doc_id and target_topic from the request to the valid response
    roadmap_data["doc_id"] = request.doc_id
    roadmap_data["target_topic"] = request.target_topic
    
    # Use Pydantic to validate the dict maps perfectly to the Class
    try:
        response_model = RoadmapResponse(**roadmap_data)
        return response_model
    except Exception as e:
        print(f"[roadmap_generator] Pydantic validation error: {e}")
        return RoadmapResponse(
            doc_id=request.doc_id,
            target_topic=request.target_topic,
            roadmap_summary="Internal validation error.",
            nodes=[],
            edges=[],
            reading_order=[],
            resource_suggestions=[],
            processing_status="failed",
            errors=[{"code": "SCHEMA_VALIDATION_ERROR", "message": str(e)}]
        )


def _call_llm(prompt: str) -> str:
    """
    Calls local Ollama model.
    """
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2}
        )
        return response["message"]["content"]
    except Exception as e:
        print(f"[roadmap_generator] Ollama call failed: {e}")
        return "{}"

def _parse_response(raw: str) -> dict | None:
    """
    Strips markdown and parses JSON.
    """
    try:
        clean = raw.strip()
        clean = re.sub(r'^```json\s*', '', clean)
        clean = re.sub(r'^```\s*', '', clean)
        clean = re.sub(r'\s*```$', '', clean)
        clean = clean.strip()

        data = json.loads(clean)
        if not isinstance(data, dict):
            return None
        return data
    except json.JSONDecodeError as e:
        print(f"[roadmap_generator] JSON decode error: {e}")
        return None
