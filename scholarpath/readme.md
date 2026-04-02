# ScholarPath — Member 1: PDF Parser + Claim Extractor

## What is ScholarPath?

ScholarPath is an AI-powered educational tool that:
1. Takes an academic research PDF as input
2. Verifies whether the citations in the paper actually support the claims being made (**Trust Gate**)
3. Generates a personalized learning roadmap for the user based on verified content

This repository contains **Member 1's work** — the foundation of the entire pipeline:
- **PDF Parser** — extracts text, sections, references, and metadata from any academic PDF
- **Claim Extractor** — uses an LLM to identify verifiable factual claims from the parsed text

Every other part of the system (citation resolver, verification agent, roadmap generator, frontend) depends on the output this module produces.

---

## What This Module Does (The Pipeline)

```
PDF File
   │
   ▼
[A] Extract full text from PDF using PyMuPDF
   │
   ▼
[B] Split text into: Body Text | References Section
   │
   ▼
[C] Parse Bibliography → list of Reference objects with ref_ids like "[1]", "[2]"
   │
   ▼
[D] Detect Sections → Introduction, Methods, Results, Conclusion etc.
   │
   ▼
[E] Extract Metadata → Title, Authors, Abstract
   │
   ▼
[F] Find Citation Sentences → only sentences that contain [1], [2] style markers
   │
   ▼
[G] LLM Claim Extractor → sends citation sentences to LLM in batches of 10
                         → LLM identifies which sentences make verifiable factual claims
                         → returns structured Claim objects
   │
   ▼
[H] Assemble ParsedPaper → single JSON object containing everything above
   │
   ▼
[I] Citation Integrity Check → every claim's citation must exist in references list
   │
   ▼
ParsedPaper saved to database ✅  ← this is "Contract 01", consumed by M2 and M3
```

---

## Output Contract (What M2 and M3 Receive)

This module produces a `ParsedPaper` JSON object — referred to as **Contract 01** across the team.

```json
{
  "doc_id": "a3f7b2c1",
  "file_name": "attention_paper.pdf",
  "title": "Attention Is All You Need",
  "authors": ["Vaswani", "Shazeer"],
  "abstract": "We propose a new simple network architecture...",
  "sections": [
    { "section_id": "s1", "heading": "Introduction", "text": "..." }
  ],
  "references": [
    { "ref_id": "[1]", "raw_text": "Vaswani et al. NeurIPS 2017..." }
  ],
  "claims": [
    {
      "claim_id": "c1",
      "claim_text": "Transformers outperform RNN-based models on long-range tasks [1].",
      "citations": ["[1]"],
      "section": "Introduction",
      "section_id": "s1",
      "priority": "high",
      "claim_type": "result",
      "sentence_index": 5
    }
  ],
  "stats": {
    "num_sections": 4,
    "num_references": 30,
    "num_claims": 12,
    "num_citation_sentences": 45
  },
  "processing_status": "success",
  "errors": []
}
```

**Critical rule:** Every `citations` value inside `claims[]` must exactly match a `ref_id` in `references[]`. M2's citation resolver depends on this foreign key relationship.

---

## Project Structure

```
scholarpath/
├── backend/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app — all HTTP endpoints
│   ├── schemas.py                 # Pydantic models: ParsedPaper, Claim, Section, Reference
│   ├── database.py                # SQLite setup + helper functions
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py          # Core PDF parsing logic (Steps A–I above)
│   │   └── claim_extractor.py     # LLM-based claim extraction
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── claim_extraction.py    # Prompt template for the LLM
│   ├── utils/
│   │   ├── __init__.py
│   │   └── citation_patterns.py   # All regex logic for citations
│   └── tests/
│       ├── __init__.py
│       └── test_parser.py         # Pytest test suite
├── contracts/                     # Sample JSON contracts shared with M2/M3
├── uploads/                       # Uploaded PDFs stored here
├── .env                           # API keys (not committed to git)
├── conftest.py                    # Pytest path configuration
├── test_run.py                    # Quick manual test script (no PDF needed)
└── README.md
```

---

## Tech Stack

| Tool | Purpose |
|---|---|
| **Python 3.11+** | Core language |
| **FastAPI** | REST API framework |
| **PyMuPDF (fitz)** | PDF text extraction |
| **Ollama + llama3.2** | Local LLM for claim extraction (free, no API key) |
| **SQLAlchemy + SQLite** | Database for storing parsed results |
| **Pydantic** | Data validation and schema enforcement |
| **Pytest** | Test suite |
| **Uvicorn** | ASGI server to run FastAPI |

---

## Setup Instructions

### 1. Prerequisites

- Python 3.11 or higher installed
- [Ollama](https://ollama.com/download) installed (for local LLM)

### 2. Clone and navigate to project

```powershell
cd scholarpath
```

### 3. Create and activate virtual environment

```powershell
python -m venv venv
venv\Scripts\activate
```

### 4. Install all dependencies

```powershell
pip install fastapi uvicorn python-multipart pymupdf ollama sqlalchemy aiofiles python-dotenv pydantic pytest
```

### 5. Create the `__init__.py` files (makes Python treat folders as packages)

```powershell
New-Item -ItemType File -Force backend/__init__.py
New-Item -ItemType File -Force backend/agents/__init__.py
New-Item -ItemType File -Force backend/utils/__init__.py
New-Item -ItemType File -Force backend/prompts/__init__.py
New-Item -ItemType File -Force backend/tests/__init__.py
```

### 6. Pull the local LLM model

```powershell
ollama pull llama3.2
```

> If low on RAM, use `ollama pull phi3` instead and update `OLLAMA_MODEL = "phi3"` in `claim_extractor.py`

### 7. Create `.env` file (no API key needed for Ollama)

```
# .env
UPLOAD_DIR=uploads
```

---

## Running the Project

### Start Ollama (keep this running in a separate terminal)

```powershell
ollama serve
```

### Start the FastAPI server

```powershell
cd scholarpath
uvicorn backend.main:app --reload
```

API will be live at: `http://127.0.0.1:8000`

Interactive API docs at: `http://127.0.0.1:8000/docs`

---

## API Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| `POST` | `/upload-pdf` | Upload a PDF file, get back a `doc_id` |
| `POST` | `/analyze/{doc_id}` | Trigger full parsing + claim extraction |
| `GET` | `/status/{doc_id}` | Check processing status |
| `GET` | `/results/{doc_id}` | Get the full ParsedPaper JSON (Contract 01) |
| `GET` | `/demo-papers` | List of preloaded demo papers |

### Quick test with curl

```powershell
# Upload a PDF
curl -X POST "http://127.0.0.1:8000/upload-pdf" -F "file=@your_paper.pdf"

# Trigger analysis (use the doc_id from above)
curl -X POST "http://127.0.0.1:8000/analyze/a3f7b2c1"

# Check status
curl "http://127.0.0.1:8000/status/a3f7b2c1"

# Get results
curl "http://127.0.0.1:8000/results/a3f7b2c1"
```

---

## Testing

### Run the full test suite

```powershell
cd scholarpath
pytest backend/tests/test_parser.py -v
```

### Run quick manual test (no PDF needed — tests LLM claim extraction directly)

```powershell
python test_run.py
```

Expected output:
```
✅ Extracted 2 claims:

  [c1] Transformer models outperform RNN-based architectures...
         citations=['[1]'], type=result, priority=high

  [c2] The attention mechanism allows the model to focus on...
         citations=['[2]', '[3]'], type=result, priority=medium
```

---

## Handoff to M2 (Citation Resolver)

Once parsing is complete, M2 can fetch Contract 01 via:

```
GET /results/{doc_id}
```

M2 depends on:
- `references[]` — to resolve citation metadata from Semantic Scholar / arXiv
- `claims[].citations` — to know which references each claim cites
- All `citations` values in `claims[]` are guaranteed to exist in `references[]` (enforced by `validate_citation_integrity()`)

---

## Common Issues

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: backend` | Make sure all `__init__.py` files exist and you're running from the `scholarpath/` folder |
| `Ollama call failed` | Run `ollama serve` in a separate terminal first |
| `0 claims extracted` | Check Ollama is running and `llama3.2` model is pulled |
| `PDF appears to be scanned` | Only text-based PDFs work — scanned image PDFs are not supported in MVP |
| Red imports in VS Code | Open VS Code from inside the `scholarpath/` folder, not a parent folder |