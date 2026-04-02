# scholarpath/test_run.py
# Run with: python test_run.py
import os
from dotenv import load_dotenv
load_dotenv()

from backend.agents.claim_extractor import extract_claims
from backend.schemas import Section

# Fake two citation sentences (no PDF needed to test the LLM step)
test_sentences = [
    {
        "sentence": "Transformer models outperform RNN-based architectures on long-range dependency tasks [1].",
        "citations": ["[1]"],
        "sentence_index": 5
    },
    {
        "sentence": "The attention mechanism allows the model to focus on relevant parts of the input sequence [2], [3].",
        "citations": ["[2]", "[3]"],
        "sentence_index": 12
    },
    {
        "sentence": "We believe future work should explore this further.",  # should be SKIPPED
        "citations": [],
        "sentence_index": 20
    }
]

test_sections = [
    Section(section_id="s1", heading="Introduction", text="intro text"),
    Section(section_id="s2", heading="Methods", text="methods text"),
]

claims = extract_claims(test_sentences, test_sections)

print(f"\n✅ Extracted {len(claims)} claims:\n")
for c in claims:
    print(f"  [{c.claim_id}] {c.claim_text[:60]}...")
    print(f"         citations={c.citations}, type={c.claim_type}, priority={c.priority}\n")