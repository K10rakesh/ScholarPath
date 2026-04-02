# backend/prompts/claim_extraction.py
# The prompt template for the LLM claim extraction step.
# {sentences} is the only placeholder — filled in at runtime.

CLAIM_EXTRACTION_PROMPT = """
You are an academic claim extractor. Below are sentences from a research paper.
Each sentence is prefixed with its index like: [idx:12] sentence text here.

Your task: identify ONLY sentences that make a VERIFIABLE FACTUAL CLAIM
that is directly backed by one or more citation markers like [1], [2].

SKIP sentences that are:
- Opinions or speculative statements ("we believe", "it seems")
- Future work or limitations ("future work should", "one limitation is")
- Pure definitions without empirical backing
- Methodology steps with no factual result claim
- Any sentence with NO citation marker at all

For every valid claim sentence, output this exact JSON object:
{{
  "claim_id": "PLACEHOLDER",
  "claim_text": "exact sentence text without the idx prefix",
  "citations": ["[1]", "[3]"],
  "section": "section heading this sentence belongs to",
  "section_id": "s1",
  "priority": "high",
  "claim_type": "result",
  "sentence_index": 12
}}

Field rules:
- claim_text: copy the exact sentence, remove the [idx:N] prefix
- citations: only include markers that actually appear in this sentence
- priority: "high" = core result/contribution, "medium" = supporting evidence, "low" = peripheral
- claim_type: one of "result" | "background" | "method" | "comparative"
- sentence_index: the integer N from the [idx:N] prefix

Return a JSON array ONLY.
No explanation. No markdown fences. No preamble. No trailing text.
If zero valid claims found, return exactly: []

Sentences:
{sentences}
"""