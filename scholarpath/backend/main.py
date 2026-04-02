# backend/main.py
# FastAPI application — all the HTTP endpoints.

import uuid
import os
import aiofiles
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from backend.schemas import ParsedPaper
from backend.agents.pdf_parser import parse_pdf
from backend.database import (
    insert_document,
    update_document_status,
    save_parsed_paper,
    get_parsed_paper,
    get_document_status
)

# Load .env variables (ANTHROPIC_API_KEY etc.)
load_dotenv()

app = FastAPI(title="ScholarPath API", version="0.1.0")

# Allow all origins for local dev — M3's React frontend needs this
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── POST /upload-pdf ───────────────────────────────────────────────────────────

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Accepts a PDF file upload. Saves it to disk. Returns a doc_id.
    Does NOT start parsing — call /analyze/{doc_id} to trigger that.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted")

    # Generate a short unique ID for this document
    doc_id = str(uuid.uuid4())[:8]
    file_path = f"{UPLOAD_DIR}/{doc_id}.pdf"

    # Save the uploaded file asynchronously
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    # Create a database record for this document
    insert_document(doc_id, file.filename)

    return {
        "doc_id": doc_id,
        "status": "uploaded",
        "file_name": file.filename
    }


# ── POST /analyze/{doc_id} ─────────────────────────────────────────────────────

@app.post("/analyze/{doc_id}")
async def analyze(doc_id: str):
    """
    Triggers the full PDF parse + claim extraction pipeline for a document.
    Stores the result in the database.
    """
    file_path = f"{UPLOAD_DIR}/{doc_id}.pdf"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"No PDF found for doc_id: {doc_id}")

    # Mark as processing before we start
    update_document_status(doc_id, "processing")

    # Run the full parser (Phase 1 + Phase 2)
    # This is synchronous for now — LangGraph async wiring comes in Phase 8
    paper: ParsedPaper = parse_pdf(file_path, doc_id)

    # Persist the result
    save_parsed_paper(doc_id, paper)

    return {
        "doc_id": doc_id,
        "status": paper.processing_status,
        "num_claims": len(paper.claims),
        "num_references": len(paper.references),
        "errors": paper.errors
    }


# ── GET /status/{doc_id} ───────────────────────────────────────────────────────

@app.get("/status/{doc_id}")
async def status(doc_id: str):
    """
    Returns current pipeline status. Used by M3 for polling the processing page.
    """
    current_status = get_document_status(doc_id)

    if current_status is None:
        raise HTTPException(status_code=404, detail=f"doc_id not found: {doc_id}")

    return {"doc_id": doc_id, "status": current_status}


# ── GET /results/{doc_id} ──────────────────────────────────────────────────────

@app.get("/results/{doc_id}")
async def results(doc_id: str):
    """
    Returns the full ParsedPaper JSON (Contract 01) for a document.
    This is what M2 and M3 consume.
    """
    current_status = get_document_status(doc_id)

    if current_status is None:
        raise HTTPException(status_code=404, detail="Document not found")

    if current_status in ("uploaded", "processing"):
        raise HTTPException(status_code=400, detail="Document is still processing")

    paper = get_parsed_paper(doc_id)

    if paper is None:
        raise HTTPException(status_code=500, detail="Result not found despite done status")

    # Return as dict — FastAPI auto-serialises to JSON
    return paper.model_dump()


# ── GET /demo-papers ───────────────────────────────────────────────────────────

@app.get("/demo-papers")
async def demo_papers():
    """
    Hardcoded list of pre-loaded demo papers for the hackathon demo.
    M3 uses this to populate the landing page demo buttons.
    """
    return [
        {
            "name": "Attention Is All You Need",
            "arxiv_id": "1706.03762",
            "domain": "Machine Learning",
            "doc_id": "demo001"
        },
        {
            "name": "BERT: Pre-training of Deep Bidirectional Transformers",
            "arxiv_id": "1810.04805",
            "domain": "Natural Language Processing",
            "doc_id": "demo002"
        }
    ]