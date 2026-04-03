# backend/agents/roadmap_generator.py

import json
import re
from typing import Optional

import ollama

from backend.schemas_member2 import (
    ParsedPaper,
    VerificationReportOutput,
    RoadmapResponseOutput,
    RoadmapNode,
    RoadmapEdge,
    ResourceSuggestion,
    ProcessingStatus,
    TrustStatus,
)
# You can adjust this to match the team's preference
OLLAMA_MODEL = "phi3"


def generate_roadmap(parsed_paper: ParsedPaper, verification_report: VerificationReportOutput) -> RoadmapResponseOutput:
    """
    Main entry point for roadmap generation.
    Takes parsed paper and verification report, produces roadmap response.
    Always generates a roadmap - uses heuristics when LLM is unavailable.
    """
    # Extract target topic from paper
    target_topic = _extract_target_topic(parsed_paper)

    # Extract key concepts from verified claims (or paper content if no verified claims)
    key_concepts = _extract_key_concepts(verification_report, parsed_paper)

    # Check trust gate - still generate roadmap but mark as cautionary
    skip_llm = False
    if verification_report.trust_report.status == TrustStatus.LOW_TRUST:
        # Don't skip - generate with heuristic and add warning
        skip_llm = True

    # Generate the roadmap using LLM (if trust is sufficient)
    roadmap = None
    if not skip_llm:
        roadmap = _generate_roadmap_with_llm(
            target_topic=target_topic,
            key_concepts=key_concepts,
            domain=parsed_paper.domain or "machine_learning",
            doc_id=parsed_paper.doc_id
        )

    # Fallback to heuristic roadmap (always works, no LLM needed)
    if roadmap is None:
        roadmap = _generate_heuristic_roadmap(
            target_topic=target_topic,
            key_concepts=key_concepts,
            doc_id=parsed_paper.doc_id
        )

    # Add trust warning if applicable
    if verification_report.trust_report.status == TrustStatus.LOW_TRUST:
        roadmap.processing_status = ProcessingStatus.PARTIAL
        roadmap.errors.append({
            "code": "LOW_TRUST",
            "message": f"Trust score {verification_report.trust_report.trust_score} is below threshold. Verify claims independently."
        })

    return roadmap


# =============================================================================
# Private helpers
# =============================================================================

def _extract_target_topic(parsed_paper: ParsedPaper) -> str:
    """
    Extract the main topic/focus of the paper.
    Uses title and abstract for context.
    """
    title = parsed_paper.title.lower()

    # Common paper title patterns
    patterns = [
        r"(.+) for (.+)",
        r"(.+) in (.+)",
        r"towards (.+)",
        r"learning (.+)",
        r"understanding (.+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            # Return the most specific part
            groups = match.groups()
            if len(groups) == 2:
                return groups[1].strip() or groups[0].strip()
            return groups[0].strip()

    # Fallback: use key terms from title
    stop_words = {"a", "an", "the", "for", "in", "on", "with", "using", "via", "towards"}
    words = [w.strip(".,;:") for w in parsed_paper.title.split()]
    key_words = [w for w in words if w.lower() not in stop_words and len(w) > 2]

    return " ".join(key_words[:5]) if key_words else "Machine Learning"


def _extract_key_concepts(
    verification_report: VerificationReportOutput,
    parsed_paper: ParsedPaper
) -> list[str]:
    """
    Extract key concepts from verified claims and paper content.
    Falls back to paper content if no verified claims exist.
    """
    concepts = set()

    # Add concepts from verified claims
    verified_claims_exist = False
    for result in verification_report.verification_results:
        if result.verdict in ("supported", "partially_supported"):
            verified_claims_exist = True
            # Extract nouns/noun phrases from claim text
            claim_concepts = _extract_concepts_from_text(result.claim_text)
            concepts.update(claim_concepts)

    # If no verified claims, extract concepts directly from paper content
    if not verified_claims_exist:
        # Extract from abstract
        if parsed_paper.abstract:
            abstract_concepts = _extract_concepts_from_text(parsed_paper.abstract)
            concepts.update(abstract_concepts)

        # Extract from section headings
        for section in parsed_paper.sections:
            heading_concepts = _extract_concepts_from_text(section.heading)
            concepts.update(heading_concepts)

        # Extract from title
        title_concepts = _extract_concepts_from_text(parsed_paper.title)
        concepts.update(title_concepts)

    # Add domain-specific concepts
    domain = (parsed_paper.domain or "machine_learning").lower()
    if "ml" in domain or "machine learning" in domain:
        concepts.add("machine learning")
    if "nlp" in domain or "natural language" in domain:
        concepts.add("natural language processing")
    if "deep" in domain:
        concepts.add("deep learning")

    return list(concepts)[:10]  # Limit to top 10 concepts


def _extract_concepts_from_text(text: str) -> list[str]:
    """
    Extract potential concepts from a text string.
    Simple heuristic: capitalized terms and technical phrases.
    """
    concepts = []

    # Look for capitalized technical terms
    matches = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', text)
    concepts.extend(matches)

    # Look for common ML/AI terms (case insensitive)
    ml_terms = [
        "transformer", "attention", "neural network", "recurrent",
        "convolutional", "encoder", "decoder", "embedding",
        "sequence model", "language model"
    ]
    text_lower = text.lower()
    for term in ml_terms:
        if term in text_lower:
            concepts.append(term.title())

    return list(set(concepts))[:5]


def _generate_roadmap_with_llm(
    target_topic: str,
    key_concepts: list[str],
    domain: str,
    doc_id: str
) -> Optional[RoadmapResponseOutput]:
    """
    Generate roadmap using LLM for intelligent prerequisite ordering.
    """
    prompt = _build_roadmap_prompt(target_topic, key_concepts, domain)

    try:
        response = _call_llm(prompt)
        parsed = _parse_roadmap_response(response, target_topic, doc_id)

        if parsed and parsed.nodes:
            return parsed

    except Exception as e:
        print(f"[roadmap_generator] LLM generation failed: {e}")

    return None


def _build_roadmap_prompt(target_topic: str, key_concepts: list[str], domain: str) -> str:
    """
    Build the prompt for roadmap generation.
    """
    concepts_str = ", ".join(key_concepts) if key_concepts else "none identified"

    return f"""You are an expert curriculum designer for {domain}. Your task is to create a learning roadmap for understanding a research paper.

TARGET TOPIC: {target_topic}
KEY CONCEPTS FROM PAPER: {concepts_str}

Generate a personalized learning roadmap that:
1. Starts with foundational prerequisites (linear algebra, probability, etc. if needed)
2. Builds up through intermediate concepts
3. Ends with the target topic

The roadmap should have 5-8 nodes total, ordered from basic to advanced.

Respond in this EXACT JSON format (no markdown):
{{
    "roadmap_summary": "One sentence explaining the learning path",
    "nodes": [
        {{
            "node_id": "n1",
            "label": "Concept Name",
            "node_type": "prerequisite" | "intermediate" | "target",
            "level": 1-5,
            "description": "Why this is needed"
        }}
    ],
    "edges": [
        {{
            "from": "n1",
            "to": "n2",
            "relation": "required_for"
        }}
    ],
    "reading_order": ["Concept 1", "Concept 2", ...],
    "resource_suggestions": [
        {{
            "topic": "Concept Name",
            "resource_type": "search_hint",
            "value": "What to search for"
        }}
    ]
}}

JSON:"""


def _call_llm(prompt: str) -> str:
    """Call local Ollama model."""
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2}
        )
        return response["message"]["content"]
    except Exception as e:
        print(f"[roadmap_generator] Ollama call failed: {e}")
        return ""


def _parse_roadmap_response(
    raw: str,
    target_topic: str,
    doc_id: str
) -> Optional[RoadmapResponseOutput]:
    """
    Parse LLM response into RoadmapResponseOutput.
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

        # Convert to RoadmapResponseOutput
        nodes = []
        for node in data.get("nodes", []):
            nodes.append(RoadmapNode(
                node_id=node.get("node_id"),
                label=node.get("label"),
                node_type=node.get("node_type", "prerequisite"),
                level=node.get("level", 1),
                description=node.get("description", "")
            ))

        edges = []
        for edge in data.get("edges", []):
            edges.append(RoadmapEdge(
                from_node=edge.get("from"),
                to_node=edge.get("to"),
                relation=edge.get("relation", "required_for")
            ))

        reading_order = data.get("reading_order", [])
        resource_suggestions = []
        for res in data.get("resource_suggestions", []):
            resource_suggestions.append(ResourceSuggestion(
                topic=res.get("topic"),
                resource_type=res.get("resource_type", "search_hint"),
                value=res.get("value")
            ))

        return RoadmapResponseOutput(
            doc_id=doc_id,
            target_topic=target_topic,
            roadmap_summary=data.get("roadmap_summary", "Learning roadmap"),
            nodes=nodes,
            edges=edges,
            reading_order=reading_order,
            resource_suggestions=resource_suggestions,
            processing_status=ProcessingStatus.SUCCESS
        )
    except json.JSONDecodeError as e:
        print(f"[roadmap_generator] JSON decode error: {e}")
        return None


def _generate_heuristic_roadmap(
    target_topic: str,
    key_concepts: list[str],
    doc_id: str
) -> RoadmapResponseOutput:
    """
    Fallback heuristic-based roadmap generation.
    """
    nodes = []
    reading_order = []

    # Add foundational concepts
    nodes.append(RoadmapNode(
        node_id="n1",
        label="Mathematical Foundations",
        node_type="prerequisite",
        level=1,
        description="Linear algebra, calculus, and probability basics"
    ))
    reading_order.append("Mathematical Foundations")

    nodes.append(RoadmapNode(
        node_id="n2",
        label="Core Domain Concepts",
        node_type="prerequisite",
        level=2,
        description="Fundamental concepts in the field"
    ))
    reading_order.append("Core Domain Concepts")

    # Add key concepts from paper
    for i, concept in enumerate(key_concepts[:3], start=3):
        nodes.append(RoadmapNode(
            node_id=f"n{i}",
            label=concept,
            node_type="intermediate",
            level=i,
            description=f"Understanding {concept}"
        ))
        reading_order.append(concept)

    # Add target topic
    nodes.append(RoadmapNode(
        node_id=f"n{len(nodes) + 1}",
        label=target_topic,
        node_type="target",
        level=len(nodes) + 1,
        description="The main topic of the paper"
    ))
    reading_order.append(target_topic)

    # Create edges
    edges = []
    for i in range(len(nodes) - 1):
        edges.append(RoadmapEdge(
            from_node=nodes[i].node_id,
            to_node=nodes[i + 1].node_id,
            relation="required_for"
        ))

    return RoadmapResponseOutput(
        doc_id=doc_id,
        target_topic=target_topic,
        roadmap_summary=f"Learn {target_topic} through {len(nodes)} structured topics",
        nodes=nodes,
        edges=edges,
        reading_order=reading_order,
        resource_suggestions=[
            ResourceSuggestion(
                topic=target_topic,
                resource_type="search_hint",
                value=f"{target_topic} tutorial for beginners"
            )
        ],
        processing_status=ProcessingStatus.SUCCESS
    )
