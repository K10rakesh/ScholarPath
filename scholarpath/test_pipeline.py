import sys
import os

sys.path.append(r"c:\Users\venom\Desktop\scholarpath\ScholarPath")
import backend.main as main
from backend.schemas_member2 import ParsedPaper, Claim

# Test the pipeline
paper_mock = ParsedPaper(
    doc_id="test_001",
    file_name="test.pdf",
    title="Attention stuff",
    authors=["Vaswani"],
    full_text="Transformers are very cool but they need attention.",
    sections=[],
    references=[{
        "ref_id": "[1]",
        "raw_text": "Vaswani et al. Attention is All You Need. NIPS 2017.",
        "citation_style": "numbered"
    }],
    claims=[
        Claim(
            claim_id="c1",
            claim_text="Attention mechanisms are needed for transformers.",
            citations=["[1]"],
            section="Intro",
            section_id="s1",
            priority="high",
            claim_type="finding",
            sentence_index=0
        )
    ],
    stats={},
    processing_status="done"
)

main.get_parsed_paper = lambda doc_id: paper_mock

async def test_run():
    print("Testing pipeline with claims...")
    res = await main.full_pipeline_endpoint("test_001")
    print("Final Trust Score:", res["trust_report"]["trust_score"])
    print("Claim 1 Verdict:", res["claims_overview"][0]["verdict"])
    print("Explanation:", res["claims_overview"][0]["explanation"])

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_run())
