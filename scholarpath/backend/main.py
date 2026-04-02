# backend/main.py
# FastAPI application — all the HTTP endpoints.

import uuid
import os
import aiofiles
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from backend.schemas import ParsedPaper
from backend.schemas_member2 import (
    ResolvedCitationsOutput,
    VerificationReportOutput,
    RoadmapResponseOutput,
    FinalReportOutput,
    PaperSummary,
    ClaimsOverviewItem,
    RoadmapSummary,
    TrustReport,
    TrustStatus,
    VerifiedClaimSummary,
    TrustReportSummary,
    RoadmapConstraints,
    RoadmapRequest,
)
from backend.agents.pdf_parser import parse_pdf
from backend.agents.citation_resolver import resolve_citations
from backend.agents.verification_agent import verify_claims
from backend.agents.roadmap_generator import generate_roadmap
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

# Root endpoint - welcome message
@app.get("/")
async def root():
    return {
        "message": "Welcome to ScholarPath API",
        "docs": "/docs",
        "endpoints": [
            "POST /upload-pdf",
            "POST /analyze/{doc_id}",
            "GET /status/{doc_id}",
            "GET /results/{doc_id}",
            "POST /resolve-citations/{doc_id}",
            "POST /verify/{doc_id}",
            "POST /generate-roadmap/{doc_id}",
            "POST /full-pipeline/{doc_id}"
        ]
    }

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
def analyze(doc_id: str):
    """
    Triggers the full PDF parse + claim extraction pipeline for a document.
    Stores the result in the database.
    """
    file_path = f"{UPLOAD_DIR}/{doc_id}.pdf"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"No PDF found for doc_id: {doc_id}")

    # Mark as processing before we start
    print(f"\n[API] → BEGINNING ANALYSIS PHASE for {doc_id}")
    update_document_status(doc_id, "processing")

    # Run the full parser (Phase 1 + Phase 2)
    # This runs synchronously in FastAPI threadpool implicitly via def endpoint
    print(f"[API] Executing local LlaMA3.2 claim extraction... (this may take 1-3 minutes)")
    paper: ParsedPaper = parse_pdf(file_path, doc_id)

    # Persist the result
    print(f"[API] ✓ Finished parsing paper '{doc_id}' ({len(paper.claims)} claims extracted)")
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


# =============================================================================
# Member 2 API Endpoints - Citation Resolution, Verification, Roadmap
# =============================================================================

# In-memory cache for Member 2 outputs (for MVP - use DB in production)
_member2_cache = {}


@app.post("/resolve-citations/{doc_id}")
async def resolve_citations_endpoint(doc_id: str):
    """
    Member 2 - Contract 02: Resolve citations to real paper metadata.
    Takes the parsed paper from Member 1 and fetches metadata from Semantic Scholar/arXiv.
    """
    # Get the parsed paper first
    paper = get_parsed_paper(doc_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Parsed paper not found. Run /analyze first.")

    # Run citation resolution
    resolved: ResolvedCitationsOutput = resolve_citations(paper)

    # Cache the result
    _member2_cache[f"{doc_id}_citations"] = resolved.model_dump()

    return resolved.model_dump()


@app.get("/citations/{doc_id}")
async def get_citations(doc_id: str):
    """
    Get resolved citations for a document.
    """
    cached = _member2_cache.get(f"{doc_id}_citations")
    if cached:
        return cached
    raise HTTPException(status_code=404, detail="Citations not resolved yet. Call /resolve-citations first.")


@app.post("/verify/{doc_id}")
async def verify_endpoint(doc_id: str):
    """
    Member 2 - Contract 03: Verify claims against cited evidence.
    Takes parsed paper + resolved citations, produces verification report with trust score.
    """
    # Get the parsed paper
    paper = get_parsed_paper(doc_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Parsed paper not found.")

    # Get resolved citations
    citations_data = _member2_cache.get(f"{doc_id}_citations")
    if not citations_data:
        # Auto-resolve if not already done
        from backend.agents.citation_resolver import resolve_citations
        resolved: ResolvedCitationsOutput = resolve_citations(paper)
        _member2_cache[f"{doc_id}_citations"] = resolved.model_dump()
    else:
        resolved = ResolvedCitationsOutput(**citations_data)

    # Run verification
    verification: VerificationReportOutput = verify_claims(paper, resolved)

    # Cache the result
    _member2_cache[f"{doc_id}_verification"] = verification.model_dump()

    return verification.model_dump()


@app.get("/verification/{doc_id}")
async def get_verification(doc_id: str):
    """
    Get verification report for a document.
    """
    cached = _member2_cache.get(f"{doc_id}_verification")
    if cached:
        return cached
    raise HTTPException(status_code=404, detail="Verification not done yet. Call /verify first.")


@app.post("/generate-roadmap/{doc_id}")
async def generate_roadmap_endpoint(doc_id: str):
    """
    Member 2 - Contract 05: Generate personalized learning roadmap.
    Takes parsed paper + verification report, produces roadmap (only if trust gate passes).
    """
    # Get the parsed paper
    paper = get_parsed_paper(doc_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Parsed paper not found.")

    # Get verification report
    verification_data = _member2_cache.get(f"{doc_id}_verification")
    if not verification_data:
        raise HTTPException(
            status_code=400,
            detail="Verification not done yet. Call /verify first."
        )

    verification = VerificationReportOutput(**verification_data)

    # Generate roadmap
    roadmap: RoadmapResponseOutput = generate_roadmap(paper, verification)
    roadmap.doc_id = doc_id

    # Cache the result
    _member2_cache[f"{doc_id}_roadmap"] = roadmap.model_dump()

    return roadmap.model_dump()


@app.get("/roadmap/{doc_id}")
async def get_roadmap(doc_id: str):
    """
    Get roadmap for a document.
    """
    cached = _member2_cache.get(f"{doc_id}_roadmap")
    if cached:
        return cached
    raise HTTPException(status_code=404, detail="Roadmap not generated yet. Call /generate-roadmap first.")


@app.post("/full-pipeline/{doc_id}")
def full_pipeline_endpoint(doc_id: str):
    """
    Run the complete Member 2 pipeline: resolve citations -> verify claims -> generate roadmap.
    Returns the combined Final Report (Contract 06).
    """
    # Step 1: Get parsed paper
    print(f"\n[API] → BEGINNING PIPELINE RESOLUTION for {doc_id}")
    paper = get_parsed_paper(doc_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Parsed paper not found.")

    # Step 2: Resolve citations
    print(f"[API] Resolving {len(paper.references)} citations globally via Semantic Scholar + ArXiv (est. ~{int(len(paper.references) * 3.2)} seconds latency padding)")
    resolved: ResolvedCitationsOutput = resolve_citations(paper)
    _member2_cache[f"{doc_id}_citations"] = resolved.model_dump()
    print(f"[API] ✓ Citations securely resolved.")

    # Step 3: Verify claims
    print(f"[API] Verifying extracted claims via LangGraph Agentic routing. Instantiating LLaMA3.2 pipeline... (this is computationally heavy)")
    verification: VerificationReportOutput = verify_claims(paper, resolved)
    _member2_cache[f"{doc_id}_verification"] = verification.model_dump()
    print(f"[API] ✓ Source constraints evaluated. Trust Level: {verification.trust_report.trust_score}")

    # Step 4: Generate roadmap
    print(f"[API] Generating roadmap parameters constraints...")
    roadmap: RoadmapResponseOutput = generate_roadmap(paper, verification)
    roadmap.doc_id = doc_id

    _member2_cache[f"{doc_id}_roadmap"] = roadmap.model_dump()

    # Step 5: Assemble final report (Contract 06)
    final_report = FinalReportOutput(
        doc_id=doc_id,
        paper=PaperSummary(
            title=paper.title,
            authors=paper.authors,
            domain=paper.domain or "unknown"
        ),
        trust_report=verification.trust_report,
        claims_overview=[
            ClaimsOverviewItem(
                claim_id=r.claim_id,
                claim_text=r.claim_text,
                citations=[r.ref_id],
                verdict=r.verdict,
                confidence=r.confidence,
                explanation=r.explanation
            )
            for r in verification.verification_results
        ],
        roadmap=RoadmapSummary(
            target_topic=roadmap.target_topic,
            nodes=roadmap.nodes,
            edges=roadmap.edges,
            reading_order=roadmap.reading_order
        ),
        processing_status=verification.processing_status,
        errors=verification.errors + roadmap.errors
    )

    _member2_cache[f"{doc_id}_final"] = final_report.model_dump()

    return final_report.model_dump()


@app.get("/final-report/{doc_id}")
async def get_final_report(doc_id: str):
    """
    Get the combined final report (Contract 06) for frontend consumption.
    """
    cached = _member2_cache.get(f"{doc_id}_final")
    if cached:
        return cached

    # Try to assemble from cached parts
    verification_data = _member2_cache.get(f"{doc_id}_verification")
    roadmap_data = _member2_cache.get(f"{doc_id}_roadmap")
    paper = get_parsed_paper(doc_id)

    if not all([verification_data, roadmap_data, paper]):
        raise HTTPException(
            status_code=404,
            detail="Run /full-pipeline first or ensure all steps are complete."
        )

    verification = VerificationReportOutput(**verification_data)
    roadmap = RoadmapResponseOutput(**roadmap_data)

    final_report = FinalReportOutput(
        doc_id=doc_id,
        paper=PaperSummary(
            title=paper.title,
            authors=paper.authors,
            domain=paper.domain or "unknown"
        ),
        trust_report=verification.trust_report,
        claims_overview=[
            ClaimsOverviewItem(
                claim_id=r.claim_id,
                claim_text=r.claim_text,
                citations=[r.ref_id],
                verdict=r.verdict,
                confidence=r.confidence,
                explanation=r.explanation
            )
            for r in verification.verification_results
        ],
        roadmap=RoadmapSummary(
            target_topic=roadmap.target_topic,
            nodes=roadmap.nodes,
            edges=roadmap.edges,
            reading_order=roadmap.reading_order
        ),
        processing_status=verification.processing_status,
        errors=verification.errors + roadmap.errors
    )

    return final_report.model_dump()
