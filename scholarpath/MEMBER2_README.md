# ScholarPath — Member 2: Citation Verification Pipeline

## Overview

This module implements the **Trust Gate** — the core innovation of ScholarPath. It verifies whether citations in an academic paper actually support the claims made, then generates a personalized learning roadmap.

## Pipeline

```
ParsedPaper (Contract 01)
    │
    ▼
[A] Citation Resolution → Fetch metadata from Semantic Scholar/arXiv
    │
    ▼
[B] Claim Verification → LLM compares claims vs cited evidence
    │
    ▼
[C] Trust Gate → Calculate trust score, decide if roadmap should be generated
    │
    ▼
[D] Roadmap Generation → Personalized learning path (only if trusted)
    │
    ▼
[E] Final Report → Combined output for frontend (Contract 06)
```

## Output Contracts

| Contract | File | Description |
|----------|------|-------------|
| 01 | `parsed_paper.json` | Input from Member 1 |
| 02 | `resolved_citations.json` | Citation metadata from APIs |
| 03 | `verification_report.json` | Claim verdicts + trust score |
| 04 | `roadmap_request.json` | Input for roadmap (derived) |
| 05 | `roadmap_response.json` | Learning roadmap with nodes/edges |
| 06 | `final_report.json` | Combined output for frontend |

---

## Project Structure

```
backend/
├── schemas_member2.py       # Pydantic models for all contracts
├── agents/
│   ├── citation_resolver.py    # Contract 02 - API calls to Semantic Scholar/arXiv
│   ├── verification_agent.py   # Contract 03 - LLM claim verification
│   └── roadmap_generator.py    # Contract 05 - Learning path generation
├── main.py                  # FastAPI endpoints (see API section below)
└── database.py              # Storage helpers
```

---

## API Endpoints

### Citation Resolution

```bash
# Resolve citations for a document
POST /resolve-citations/{doc_id}

# Get resolved citations
GET /citations/{doc_id}
```

### Verification

```bash
# Verify claims against cited evidence
POST /verify/{doc_id}

# Get verification report
GET /verification/{doc_id}
```

### Roadmap Generation

```bash
# Generate learning roadmap
POST /generate-roadmap/{doc_id}

# Get roadmap
GET /roadmap/{doc_id}
```

### Full Pipeline

```bash
# Run all steps and get combined report
POST /full-pipeline/{doc_id}

# Get final report
GET /final-report/{doc_id}
```

---

## Testing

### Run the test suite

```bash
python test_member2.py
```

This runs:
1. Citation resolution test (Contract 02)
2. Verification test (Contract 03)
3. Roadmap generation test (Contract 05)
4. Full pipeline test

Output files are saved to `contracts/` for inspection.

---

## Key Implementation Details

### 1. Citation Resolver (`citation_resolver.py`)

**Strategy:**
1. Extract title from bibliography entry using regex patterns
2. Search Semantic Scholar API first (best coverage)
3. Fall back to arXiv API (good for CS/ML)
4. Calculate confidence based on title similarity and data completeness

**Confidence scoring:**
- Base: 0.5 for any match
- Title similarity boost: up to +0.4
- Abstract present: +0.05
- Authors present: +0.03
- Year present: +0.02
- Max: 1.0

### 2. Verification Agent (`verification_agent.py`)

**LLM Prompt Structure:**
- Presents claim and evidence side-by-side
- Asks for structured JSON verdict
- Verdicts: `supported`, `partially_supported`, `unsupported`, `insufficient_evidence`

**Trust Score Calculation:**
```python
VERDICT_SCORES = {
    "supported": 1.0,
    "partially_supported": 0.6,
    "insufficient_evidence": 0.3,
    "unsupported": 0.0,
    "unresolved": 0.0
}
trust_score = average(verdict_scores) * 100
```

**Trust Status Thresholds:**
- `trusted`: 75+
- `caution`: 45-74
- `low_trust`: below 45

### 3. Roadmap Generator (`roadmap_generator.py`)

**Two-tier approach:**
1. Try LLM-based generation first (intelligent prerequisite ordering)
2. Fall back to heuristic-based roadmap if LLM fails

**Trust Gate Logic:**
- If `trust_status == "low_trust"`: Skip roadmap generation, return error
- Otherwise: Generate full learning path

**Node Types:**
- `prerequisite`: Foundational concepts (level 1-2)
- `intermediate`: Core domain concepts (level 2-4)
- `target`: The paper's main topic (highest level)

---

## Sample JSON Outputs

See the `contracts/` folder for sample outputs:

- `02_resolved_citations.sample.json`
- `03_verification_report.sample.json`
- `04_roadmap_request.sample.json`
- `05_roadmap_response.sample.json`
- `06_final_report.sample.json`

---

## Error Handling

All modules follow these patterns:

1. **Graceful degradation**: If Semantic Scholar fails, try arXiv. If LLM fails, use heuristics.
2. **Structured errors**: Every output has `processing_status` and `errors` fields.
3. **Confidence scoring**: Low-confidence matches are still returned but flagged.

### Standard Error Format

```json
{
  "processing_status": "partial",
  "errors": [
    {
      "code": "RESOLUTION_ERROR",
      "message": "Failed to resolve [7]: API timeout"
    }
  ]
}
```

---

## Dependencies

```
fastapi
uvicorn
pydantic
ollama          # Local LLM (free, no API key needed)
httpx           # For API calls to Semantic Scholar/arXiv
python-dotenv
```

Install:
```bash
pip install fastapi uvicorn pydantic ollama httpx python-dotenv
```

---

## Integration with Member 1 and Member 3

### Input from Member 1 (Contract 01)

Member 2 expects a `ParsedPaper` object with:
- `references[]`: List of bibliography entries with `ref_id` in `[N]` format
- `claims[]`: List of claims with `citations` array matching `ref_id` values

**Critical**: Every citation in `claims[].citations` must exist in `references[].ref_id`. This is validated by `ParsedPaper.validate_citation_integrity()`.

### Output to Member 3 (Contract 05 + 06)

Member 3 consumes:
- `roadmap_response.json`: Nodes, edges, reading order for visualization
- `final_report.json`: Combined trust score + claims overview + roadmap

---

## API Usage Example

```bash
# 1. Upload PDF (Member 1)
curl -X POST "http://localhost:8000/upload-pdf" -F "file=@paper.pdf"
# Returns: {"doc_id": "a3f7b2c1", ...}

# 2. Parse PDF (Member 1)
curl -X POST "http://localhost:8000/analyze/a3f7b2c1"

# 3. Resolve Citations (Member 2)
curl -X POST "http://localhost:8000/resolve-citations/a3f7b2c1"

# 4. Verify Claims (Member 2)
curl -X POST "http://localhost:8000/verify/a3f7b2c1"

# 5. Generate Roadmap (Member 2)
curl -X POST "http://localhost:8000/generate-roadmap/a3f7b2c1"

# 6. Get Full Report (Member 2)
curl -X POST "http://localhost:8000/full-pipeline/a3f7b2c1"
```

---

## Trust Gate Decision Tree

```
Verification Results
    │
    ▼
Calculate Trust Score
    │
    ├─ Score >= 75 → Status: "trusted" → Generate full roadmap
    │
    ├─ Score 45-74 → Status: "caution" → Generate roadmap with warning labels
    │
    └─ Score < 45 → Status: "low_trust" → Skip roadmap, show warning
```

---

## Future Improvements

1. **Full-text verification**: Currently uses abstracts only. Could fetch full text for paywall-free papers.
2. **Multi-citation verification**: When a claim cites multiple papers, verify against all of them.
3. **Dual-model consensus**: Use two LLMs for verification to reduce hallucination.
4. **Caching**: Cache API responses to reduce redundant calls.
5. **Database persistence**: Store verification results in database instead of memory cache.
