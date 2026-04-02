import sys
import os

# Add the root directory to path so we can import backend models
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.schemas import RoadmapRequest, TrustReport, VerifiedClaimSimple
from backend.agents.roadmap_generator import generate_roadmap

def test_member_3_logic():
    print("====== SCHOLARPATH MEMBER 3 TEST ======")
    print("1. Building Mock Roadmap Request from Contract 04...")
    
    request = RoadmapRequest(
        doc_id="paper_001",
        title="Attention Is All You Need",
        domain="machine_learning",
        trust_report=TrustReport(
            trust_score=81,
            status="trusted",
            summary="Key claims supported."
        ),
        verified_claims=[
            VerifiedClaimSimple(
                claim_id="c1",
                claim_text="Attention mechanisms are integral to sequence modeling.",
                verdict="supported",
                confidence=0.88
            )
        ],
        target_topic="Attention Mechanism",
        key_concepts=[
            "matrices",
            "softmax",
            "neural networks",
            "attention mechanism"
        ],
        constraints={
            "only_generate_if_trusted": True,
            "max_nodes": 4
        }
    )

    print("2. Firing request to LLM (Ollama - phi3) via Roadmap Generator...")
    print("(This might take 5-15 seconds if Ollama is running...)\n")
    
    response = generate_roadmap(request)

    print("\n====== RESULT ======")
    print(f"Status: {response.processing_status}")
    
    if response.processing_status == "failed":
        print(f"Errors encountered:\n{response.errors}")
        print("\nHINT: If the error is LLM_PARSE_ERROR, it means Ollama is not running on your machine.")
        print("To fix: Install Ollama, and run 'ollama run phi3' in your terminal.")
    else:
        print(f"Summary: {response.roadmap_summary}\n")
        print("Generated Nodes:")
        for idx, node in enumerate(response.nodes, start=1):
            print(f"  {idx}. {node.label} (Level {node.level} - {node.node_type})")
            print(f"     Description: {node.description}")
        
        print("\nEdges Generated:")
        for edge in response.edges:
            print(f"  {edge.from_node} -> {edge.to}")

if __name__ == "__main__":
    test_member_3_logic()
