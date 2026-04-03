# =============================================================================
# backend/main.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   This is the FastAPI application — the single HTTP entry point for the entire
#   ScholarPath backend. Every request from the React frontend, and every call
#   between pipeline stages, goes through endpoints defined here.
#
# CONNECTED TO:
#   ← frontend/src/api.js        (makes all fetch() calls to these endpoints)
#   → backend/database.py        (reads/writes documents and parsed papers)
#   → backend/agents/pdf_parser.py          (POST /analyze)
#   → backend/agents/citation_resolver.py   (POST /resolve-citations, /full-pipeline)
#   → backend/agents/verification_agent.py  (POST /verify, /full-pipeline)
#   → backend/agents/roadmap_generator.py   (POST /generate-roadmap, /full-pipeline)
#   → backend/schemas.py & schemas_member2.py (Pydantic types for request/response)
# =============================================================================

import uuid
import os
import aiofiles
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import the Contract 01 model (Member 1's output shape)
from backend.schemas import ParsedPaper

# Import all Contract 02-06 Pydantic models (Member 2's data shapes)
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

# Import the four agent functions — each one is a pipeline stage
from backend.agents.pdf_parser import parse_pdf
from backend.agents.citation_resolver import resolve_citations
from backend.agents.verification_agent import verify_claims
from backend.agents.roadmap_generator import generate_roadmap

# Import database helper functions for persisting documents
from backend.database import (
    insert_document,
    update_document_status,
    save_parsed_paper,
    get_parsed_paper,
    get_document_status
)

# Load .env variables (e.g. ANTHROPIC_API_KEY if switching to cloud LLM, UPLOAD_DIR)
load_dotenv()

# Create the FastAPI app instance — this is also what uvicorn serves
app = FastAPI(title="ScholarPath API", version="0.1.0")


# ── Root endpoint ─────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    """
    Health check and API discovery.
    Returns a directory of all available endpoints.
    Used by developers to quickly understand what routes exist.
    """
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


# ── CORS Middleware ───────────────────────────────────────────────────────────
# Allow all origins so the Vite dev server (localhost:5173) can hit this API
# (localhost:8000) without browser security blocks during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Upload directory — where PDF files are stored on disk between pipeline stages
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)  # creates folder if it doesn't exist yet


# =============================================================================
# PHASE 1: PDF Upload and Analysis (Member 1)
# =============================================================================

# ── POST /upload-pdf ──────────────────────────────────────────────────────────
@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Step 1 of the pipeline: accept the raw PDF file.

    WHY SEPARATE FROM /analyze:
      Uploading and parsing are intentionally split so the frontend can
      show an intermediate state and poll for progress, rather than
      waiting on a single long-running request.

    WHAT IT DOES:
      1. Validates that the file is a PDF (by extension)
      2. Generates a short unique doc_id (first 8 chars of UUID)
      3. Saves the file to disk asynchronously (aiofiles to avoid blocking)
      4. Creates a "uploaded" record in the database
      5. Returns doc_id to the frontend

    CONNECTS TO: database.insert_document()
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted")

    # Generate a short, unique ID for this document (8-char UUID prefix)
    doc_id = str(uuid.uuid4())[:8]
    file_path = f"{UPLOAD_DIR}/{doc_id}.pdf"

    # Save asynchronously to avoid blocking the event loop during file I/O
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    # Register this document in the database with "uploaded" status
    insert_document(doc_id, file.filename)

    return {
        "doc_id": doc_id,
        "status": "uploaded",
        "file_name": file.filename
    }


# ── POST /analyze/{doc_id} ────────────────────────────────────────────────────
@app.post("/analyze/{doc_id}")
def analyze(doc_id: str):
    """
    Step 2: Trigger the full PDF parse + claim extraction pipeline.

    WHY SYNC (def not async def):
      parse_pdf() calls the local Ollama LLM which is CPU-bound and takes
      1-3 minutes. Making it sync runs it in FastAPI's thread pool, which
      is fine for this use case. Do NOT make it async — it would block
      the event loop.

    WHAT IT DOES:
      1. Finds the saved PDF on disk
      2. Sets status to "processing" in DB
      3. Calls parse_pdf() which:
           - extracts text via PyMuPDF
           - detects sections
           - parses bibliography
           - calls Ollama LLM for claim extraction
      4. Saves the ParsedPaper result to DB
      5. Returns summary stats

    CONNECTS TO:
      database.update_document_status()
      agents/pdf_parser.parse_pdf()
      database.save_parsed_paper()
    """
    file_path = f"{UPLOAD_DIR}/{doc_id}.pdf"

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"No PDF found for doc_id: {doc_id}")

    # Mark as processing before we start — frontend polls /status and shows spinner
    print(f"\n[API] → BEGINNING ANALYSIS PHASE for {doc_id}")
    update_document_status(doc_id, "processing")

    # Run the full parser (Phase 1 text extraction + Phase 2 LLM claim extraction)
    # This is the slow step — llama3.2 takes 1-3 minutes depending on paper length
    print(f"[API] Executing local LlaMA3.2 claim extraction... (this may take 1-3 minutes)")
    paper: ParsedPaper = parse_pdf(file_path, doc_id)

    # Persist the ParsedPaper JSON to SQLite (status also updated inside save_parsed_paper)
    print(f"[API] ✓ Finished parsing paper '{doc_id}' ({len(paper.claims)} claims extracted)")
    save_parsed_paper(doc_id, paper)

    return {
        "doc_id": doc_id,
        "status": paper.processing_status,
        "num_claims": len(paper.claims),
        "num_references": len(paper.references),
        "errors": paper.errors
    }


# ── GET /status/{doc_id} ──────────────────────────────────────────────────────
@app.get("/status/{doc_id}")
async def status(doc_id: str):
    """
    Step 3 (polling): Returns current processing status.

    WHY NEEDED:
      Since /analyze is long-running, the frontend polls this endpoint
      every 2 seconds to know when analysis completes.
      Status transitions: uploaded → processing → success/partial/failed

    CONNECTS TO: database.get_document_status()
    """
    current_status = get_document_status(doc_id)

    if current_status is None:
        raise HTTPException(status_code=404, detail=f"doc_id not found: {doc_id}")

    return {"doc_id": doc_id, "status": current_status}


# ── GET /results/{doc_id} ─────────────────────────────────────────────────────
@app.get("/results/{doc_id}")
async def results(doc_id: str):
    """
    Returns the full ParsedPaper JSON (Contract 01) after analysis completes.

    WHY: Member 2 and the frontend both need the parsed paper data.
    The full JSON includes title, authors, abstract, sections, references,
    and all extracted claims.

    CONNECTS TO: database.get_parsed_paper()
    """
    current_status = get_document_status(doc_id)

    if current_status is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Guard: don't return partial results while still processing
    if current_status in ("uploaded", "processing"):
        raise HTTPException(status_code=400, detail="Document is still processing")

    paper = get_parsed_paper(doc_id)

    if paper is None:
        raise HTTPException(status_code=500, detail="Result not found despite done status")

    # model_dump() converts Pydantic → plain dict → FastAPI auto-serialises to JSON
    return paper.model_dump()


# ── GET /demo-papers ──────────────────────────────────────────────────────────
@app.get("/demo-papers")
async def demo_papers():
    """
    Hardcoded demo paper list for hackathon judging.
    Allows judges to try the app with pre-loaded famous ML papers
    without uploading a file manually.
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
# PHASE 2+3: Member 2 Endpoints — Citation Resolution, Verification, Roadmap
# =============================================================================

# WHY IN-MEMORY CACHE:
#   For MVP speed, Member 2's outputs (resolved citations, verification report,
#   roadmap) are stored in this dict keyed by "{doc_id}_{stage}".
#   In production, these would go into separate DB tables.
_member2_cache = {}


# ── POST /resolve-citations/{doc_id} ─────────────────────────────────────────
@app.post("/resolve-citations/{doc_id}")
async def resolve_citations_endpoint(doc_id: str):
    """
    Contract 02: Resolve bibliography entries to real paper metadata.

    WHAT IT DOES:
      Reads the ParsedPaper from DB → calls citation_resolver.resolve_citations()
      which searches Semantic Scholar and arXiv APIs for each reference →
      returns resolved metadata (title, abstract, DOI, year, URL).

    NOTE: This is slow due to 3.5s API throttle per reference.
    CONNECTS TO:
      database.get_parsed_paper()
      agents/citation_resolver.resolve_citations()
    """
    paper = get_parsed_paper(doc_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Parsed paper not found. Run /analyze first.")

    # Fetch real metadata for all bibliography entries
    resolved: ResolvedCitationsOutput = resolve_citations(paper)

    # Cache result in memory for downstream steps
    _member2_cache[f"{doc_id}_citations"] = resolved.model_dump()

    return resolved.model_dump()


# ── GET /citations/{doc_id} ───────────────────────────────────────────────────
@app.get("/citations/{doc_id}")
async def get_citations(doc_id: str):
    """
    Returns cached resolved citations for a document.
    Must have called /resolve-citations first.
    """
    cached = _member2_cache.get(f"{doc_id}_citations")
    if cached:
        return cached
    raise HTTPException(status_code=404, detail="Citations not resolved yet. Call /resolve-citations first.")


# ── POST /verify/{doc_id} ─────────────────────────────────────────────────────
@app.post("/verify/{doc_id}")
async def verify_endpoint(doc_id: str):
    """
    Contract 03: Verify claims against cited evidence using LangGraph + LLM.

    WHAT IT DOES:
      1. Gets parsed paper from DB
      2. Gets resolved citations (auto-resolves if not cached)
      3. Calls verification_agent.verify_claims() which runs the LangGraph
         multi-agent pipeline for each claim-citation pair
      4. Returns verification report with Trust Score (0-100)

    CONNECTS TO:
      agents/verification_agent.verify_claims()
      agents/citation_resolver.resolve_citations() (if citations not cached)
    """
    paper = get_parsed_paper(doc_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Parsed paper not found.")

    citations_data = _member2_cache.get(f"{doc_id}_citations")
    if not citations_data:
        # Auto-resolve citations if they haven't been resolved yet
        from backend.agents.citation_resolver import resolve_citations
        resolved: ResolvedCitationsOutput = resolve_citations(paper)
        _member2_cache[f"{doc_id}_citations"] = resolved.model_dump()
    else:
        # Reconstruct Pydantic object from cached dict
        resolved = ResolvedCitationsOutput(**citations_data)

    # Run the LangGraph verification workflow for each claim
    verification: VerificationReportOutput = verify_claims(paper, resolved)

    _member2_cache[f"{doc_id}_verification"] = verification.model_dump()

    return verification.model_dump()


# ── GET /verification/{doc_id} ────────────────────────────────────────────────
@app.get("/verification/{doc_id}")
async def get_verification(doc_id: str):
    """Returns cached verification report. Must run /verify first."""
    cached = _member2_cache.get(f"{doc_id}_verification")
    if cached:
        return cached
    raise HTTPException(status_code=404, detail="Verification not done yet. Call /verify first.")


# ── POST /generate-roadmap/{doc_id} ──────────────────────────────────────────
@app.post("/generate-roadmap/{doc_id}")
async def generate_roadmap_endpoint(doc_id: str):
    """
    Contract 05: Generate the personalized learning roadmap.

    WHAT IT DOES:
      Takes the verified claims + trust report and calls roadmap_generator
      to create a prerequisite-ordered learning path. Only runs via LLM
      if the trust gate passes; otherwise uses a heuristic template.

    CONNECTS TO:
      agents/roadmap_generator.generate_roadmap()
    """
    paper = get_parsed_paper(doc_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Parsed paper not found.")

    verification_data = _member2_cache.get(f"{doc_id}_verification")
    if not verification_data:
        raise HTTPException(
            status_code=400,
            detail="Verification not done yet. Call /verify first."
        )

    verification = VerificationReportOutput(**verification_data)

    # Generate roadmap — uses LLM if trust is high enough, heuristics otherwise
    roadmap: RoadmapResponseOutput = generate_roadmap(paper, verification)
    roadmap.doc_id = doc_id

    _member2_cache[f"{doc_id}_roadmap"] = roadmap.model_dump()

    return roadmap.model_dump()


# ── GET /roadmap/{doc_id} ─────────────────────────────────────────────────────
@app.get("/roadmap/{doc_id}")
async def get_roadmap(doc_id: str):
    """Returns cached roadmap. Must run /generate-roadmap first."""
    cached = _member2_cache.get(f"{doc_id}_roadmap")
    if cached:
        return cached
    raise HTTPException(status_code=404, detail="Roadmap not generated yet. Call /generate-roadmap first.")


# ── POST /full-pipeline/{doc_id} ──────────────────────────────────────────────
@app.post("/full-pipeline/{doc_id}")
def full_pipeline_endpoint(doc_id: str):
    """
    THE MAIN ENDPOINT: Run the complete Member 2 pipeline in one call.
    This is what the frontend calls after /analyze completes.

    PIPELINE STAGES (sequential, each uses the previous step's output):
      1. Get parsed paper from DB (Contract 01, already done by /analyze)
      2. resolve_citations() → Contract 02
      3. verify_claims() → Contract 03 + Trust Gate
      4. generate_roadmap() → Contract 05
      5. Assemble FinalReportOutput → Contract 06

    WHY SYNC:
      This runs 3 sequential long-running stages. Making it sync puts it
      in FastAPI's thread pool — correct behavior for blocking operations.

    RETURNS: Contract 06 (FinalReportOutput) — the full combined report
             that the frontend renders on the results page.

    CONNECTS TO: All four agent modules + database
    """
    print(f"\n[API] → BEGINNING PIPELINE RESOLUTION for {doc_id}")
    paper = get_parsed_paper(doc_id)
    if paper is None:
        raise HTTPException(status_code=404, detail="Parsed paper not found.")

    # ── Stage 1: Resolve citations via Semantic Scholar / arXiv ────────────────
    # Rate-limited to ~3.5s per reference → expect ~N*3.5 seconds for N references
    print(f"[API] Resolving {len(paper.references)} citations globally via Semantic Scholar + ArXiv"
          f" (est. ~{int(len(paper.references) * 3.2)} seconds latency padding)")
    resolved: ResolvedCitationsOutput = resolve_citations(paper)
    _member2_cache[f"{doc_id}_citations"] = resolved.model_dump()
    print(f"[API] ✓ Citations securely resolved.")

    # ── Stage 2: Verify claims with LangGraph multi-agent workflow ──────────────
    # Each claim goes through: SourceFetcher → ClaimVerifier → TrustCalculator
    print(f"[API] Verifying extracted claims via LangGraph Agentic routing. Instantiating LLaMA3.2 pipeline... (this is computationally heavy)")
    verification: VerificationReportOutput = verify_claims(paper, resolved)
    _member2_cache[f"{doc_id}_verification"] = verification.model_dump()
    print(f"[API] ✓ Source constraints evaluated. Trust Level: {verification.trust_report.trust_score}")

    # ── Stage 3: Generate learning roadmap ─────────────────────────────────────
    # Trust gate: if score < 45 → uses heuristic template + adds LOW_TRUST warning
    print(f"[API] Generating roadmap parameters constraints...")
    roadmap: RoadmapResponseOutput = generate_roadmap(paper, verification)
    roadmap.doc_id = doc_id
    _member2_cache[f"{doc_id}_roadmap"] = roadmap.model_dump()

    # ── Stage 4: Assemble the combined Final Report (Contract 06) ───────────────
    # This is what the frontend actually renders — it combines all three contracts
    final_report = FinalReportOutput(
        doc_id=doc_id,
        paper=PaperSummary(
            title=paper.title,
            authors=paper.authors,
            domain=paper.domain or "unknown"
        ),
        trust_report=verification.trust_report,
        claims_overview=[
            # Flatten each verification result into a simplified ClaimsOverviewItem
            ClaimsOverviewItem(
                claim_id=r.claim_id,
                claim_text=r.claim_text,
                citations=[r.ref_id],         # only the primary citation
                verdict=r.verdict,
                confidence_score=r.confidence_score,
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
        errors=verification.errors + roadmap.errors   # merge errors from both stages
    )

    _member2_cache[f"{doc_id}_final"] = final_report.model_dump()

    return final_report.model_dump()


# ── GET /final-report/{doc_id} ────────────────────────────────────────────────
@app.get("/final-report/{doc_id}")
async def get_final_report(doc_id: str):
    """
    Returns Contract 06 (the combined final report) for frontend rendering.

    WHY: After /full-pipeline, the frontend can fetch this at any time
    (e.g. page refresh). If not cached, tries to assemble from cached parts.

    CONNECTS TO: _member2_cache + database.get_parsed_paper()
    """
    # Return from cache if full pipeline was already run
    cached = _member2_cache.get(f"{doc_id}_final")
    if cached:
        return cached

    # Try to assemble from individual cached parts (partial pipeline)
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

    # Assemble the same way as /full-pipeline does
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
                confidence_score=r.confidence_score,
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
