# test_member2.py
# Test script for Member 2's portion: Citation Resolution, Verification, Roadmap
# Run this to verify Member 2's code works correctly

import json
from backend.schemas_member2 import (
    ParsedPaper,
    Reference,
    Section,
    Claim,
    ResolvedCitationsOutput,
    VerificationReportOutput,
    RoadmapResponseOutput,
)
from backend.agents.citation_resolver import resolve_citations
from backend.agents.verification_agent import verify_claims
from backend.agents.roadmap_generator import generate_roadmap


def create_mock_parsed_paper() -> ParsedPaper:
    """Create a mock ParsedPaper for testing (simulates Member 1's output)."""
    return ParsedPaper(
        doc_id="test_001",
        file_name="test_paper.pdf",
        title="Attention Is All You Need",
        authors=["Vaswani", "Shazeer", "Parmar"],
        source_type="pdf_upload",
        domain="machine_learning",
        abstract="We propose a new simple network architecture, the Transformer, based solely on attention mechanisms.",
        full_text="Full paper text here...",
        sections=[
            Section(
                section_id="s1",
                heading="Introduction",
                text="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks."
            ),
            Section(
                section_id="s2",
                heading="Background",
                text="Attention mechanisms have become an integral part of sequence modeling."
            )
        ],
        references=[
            Reference(
                ref_id="[1]",
                raw_text="Bahdanau, Cho, and Bengio. Neural machine translation by jointly learning to align and translate. 2014.",
                citation_style="numbered"
            ),
            Reference(
                ref_id="[2]",
                raw_text="Gehring et al. Convolutional Sequence to Sequence Learning. 2017.",
                citation_style="numbered"
            )
        ],
        claims=[
            Claim(
                claim_id="c1",
                claim_text="The Transformer allows significantly more parallelization than recurrent sequence models.",
                citations=["[2]"],
                section="Introduction",
                section_id="s1",
                priority="high",
                claim_type="result",
                sentence_index=5
            ),
            Claim(
                claim_id="c2",
                claim_text="Attention mechanisms have become an integral part of sequence modeling and transduction models.",
                citations=["[1]"],
                section="Background",
                section_id="s2",
                priority="medium",
                claim_type="background",
                sentence_index=12
            )
        ],
        stats={
            "num_sections": 2,
            "num_references": 2,
            "num_claims": 2
        },
        processing_status="success",
        errors=[]
    )


def test_citation_resolution():
    """Test Contract 02: Citation Resolution."""
    print("\n" + "=" * 60)
    print("TEST 1: Citation Resolution (Contract 02)")
    print("=" * 60)

    paper = create_mock_parsed_paper()
    resolved: ResolvedCitationsOutput = resolve_citations(paper)

    print(f"\nDoc ID: {resolved.doc_id}")
    print(f"Processing Status: {resolved.processing_status}")
    print(f"\nStats: {resolved.stats}")

    print("\nResolved Citations:")
    for citation in resolved.resolved_citations:
        print(f"\n  [{citation.ref_id}]")
        print(f"    Status: {citation.resolution_status}")
        print(f"    Title: {citation.matched_title or 'N/A'}")
        print(f"    Confidence: {citation.confidence:.2f}")
        print(f"    Source: {citation.source_provider or 'N/A'}")

    # Validate output shape
    assert resolved.doc_id == "test_001"
    assert len(resolved.resolved_citations) == 2
    assert resolved.stats["total_references"] == 2

    print("\n✅ Citation Resolution Test PASSED")
    return resolved


def test_verification(report: ResolvedCitationsOutput):
    """Test Contract 03: Verification Report."""
    print("\n" + "=" * 60)
    print("TEST 2: Claim Verification (Contract 03)")
    print("=" * 60)

    paper = create_mock_parsed_paper()

    verification: VerificationReportOutput = verify_claims(paper, report)

    print(f"\nDoc ID: {verification.doc_id}")
    print(f"Processing Status: {verification.processing_status}")

    print("\nTrust Report:")
    print(f"  Trust Score: {verification.trust_report.trust_score}/100")
    print(f"  Status: {verification.trust_report.status}")
    print(f"  Summary: {verification.trust_report.summary}")

    print("\nVerification Results:")
    for result in verification.verification_results:
        print(f"\n  [{result.verification_id}] Claim: {result.claim_id}")
        print(f"    Verdict: {result.verdict.value}")
        print(f"    Confidence: {result.confidence:.2f}")
        print(f"    Explanation: {result.explanation[:100]}...")

    # Validate output shape
    assert verification.doc_id == "test_001"
    assert len(verification.verification_results) == 2
    assert verification.trust_report.trust_score >= 0
    assert verification.trust_report.trust_score <= 100

    print("\n✅ Verification Test PASSED")
    return verification


def test_roadmap_generation(verification: VerificationReportOutput):
    """Test Contract 05: Roadmap Response."""
    print("\n" + "=" * 60)
    print("TEST 3: Roadmap Generation (Contract 05)")
    print("=" * 60)

    paper = create_mock_parsed_paper()

    roadmap: RoadmapResponseOutput = generate_roadmap(paper, verification)

    print(f"\nDoc ID: {roadmap.doc_id}")
    print(f"Target Topic: {roadmap.target_topic}")
    print(f"Summary: {roadmap.roadmap_summary}")
    print(f"Processing Status: {roadmap.processing_status}")

    print(f"\nNodes ({len(roadmap.nodes)}):")
    for node in roadmap.nodes:
        print(f"  [{node.node_id}] {node.label} ({node.node_type.value}) - Level {node.level}")

    print(f"\nEdges ({len(roadmap.edges)}):")
    for edge in roadmap.edges:
        print(f"  {edge.from_node} -> {edge.to_node} ({edge.relation})")

    print(f"\nReading Order: {roadmap.reading_order}")

    # Validate output shape
    assert roadmap.doc_id == "test_001"
    assert len(roadmap.nodes) > 0
    assert len(roadmap.edges) > 0

    print("\n✅ Roadmap Generation Test PASSED")
    return roadmap


def test_full_pipeline():
    """Run the complete Member 2 pipeline."""
    print("\n" + "=" * 60)
    print("FULL MEMBER 2 PIPELINE TEST")
    print("=" * 60)

    # Step 1: Create mock parsed paper (Member 1's output)
    paper = create_mock_parsed_paper()
    print(f"\n[Step 1] Loaded parsed paper: {paper.title}")
    print(f"  Claims: {len(paper.claims)}")
    print(f"  References: {len(paper.references)}")

    # Step 2: Resolve citations (Contract 02)
    print("\n[Step 2] Resolving citations...")
    resolved = resolve_citations(paper)
    resolved_count = sum(
        1 for c in resolved.resolved_citations
        if c.resolution_status.value in ("resolved", "partially_resolved")
    )
    print(f"  Resolved: {resolved_count}/{len(resolved.resolved_citations)}")

    # Step 3: Verify claims (Contract 03)
    print("\n[Step 3] Verifying claims...")
    verification = verify_claims(paper, resolved)
    print(f"  Trust Score: {verification.trust_report.trust_score}/100")
    print(f"  Status: {verification.trust_report.status.value}")

    # Step 4: Generate roadmap (Contract 05)
    print("\n[Step 4] Generating roadmap...")
    roadmap = generate_roadmap(paper, verification)
    print(f"  Nodes: {len(roadmap.nodes)}")
    print(f"  Edges: {len(roadmap.edges)}")

    print("\n" + "=" * 60)
    print("✅ FULL PIPELINE TEST COMPLETED")
    print("=" * 60)

    return {
        "paper": paper,
        "resolved": resolved,
        "verification": verification,
        "roadmap": roadmap
    }


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("SCHOLARPATH - MEMBER 2 TEST SUITE")
    print("Testing: Citation Resolution, Verification, Roadmap Generation")
    print("=" * 60)

    try:
        # Run individual tests
        resolved = test_citation_resolution()
        verification = test_verification(resolved)
        roadmap = test_roadmap_generation(verification)

        # Run full pipeline
        results = test_full_pipeline()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)

        # Save outputs to contracts folder for verification
        import os
        os.makedirs("contracts", exist_ok=True)

        with open("contracts/test_02_resolved.json", "w") as f:
            json.dump(results["resolved"].model_dump(), f, indent=2)

        with open("contracts/test_03_verification.json", "w") as f:
            json.dump(results["verification"].model_dump(), f, indent=2)

        with open("contracts/test_05_roadmap.json", "w") as f:
            json.dump(results["roadmap"].model_dump(), f, indent=2)

        print("\nOutput files saved to contracts/ folder:")
        print("  - contracts/test_02_resolved.json")
        print("  - contracts/test_03_verification.json")
        print("  - contracts/test_05_roadmap.json")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
