# =============================================================================
# backend/database.py
# =============================================================================
# WHAT THIS FILE DOES (Overall):
#   Defines the SQLite database schema and provides simple helper functions
#   that hide all SQL/ORM logic from the rest of the app. main.py imports
#   these helpers directly — no other file should touch SQLAlchemy directly.
#
# DATABASE DESIGN:
#   - Single SQLite file: backend/scholarpath.db
#   - Two tables:
#       1. `documents`      — one row per uploaded PDF, stores status + full JSON
#       2. `citation_cache` — designed for caching API lookups by title hash
#                             (not fully used in MVP; placeholder for production)
#
# CONNECTED TO:
#   ← backend/main.py         (imports all helper functions)
#   ← backend/schemas.py      (imports ParsedPaper for type hints)
# =============================================================================

import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime, Float
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.schemas import ParsedPaper


# ── Database Engine Setup ─────────────────────────────────────────────────────

# SQLite file path (relative to where uvicorn is started from — the scholarpath/ root)
DATABASE_URL = "sqlite:///./backend/scholarpath.db"

# check_same_thread=False needed for SQLite in FastAPI's multi-threaded environment
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# SessionLocal is a factory — call SessionLocal() to get a new DB session
SessionLocal = sessionmaker(bind=engine)

# Base class for all ORM table definitions
Base = declarative_base()


# ── Table Definitions ─────────────────────────────────────────────────────────

class DocumentRecord(Base):
    """
    One row per uploaded PDF document.
    Stores the doc_id, filename, current processing status, and the full
    ParsedPaper JSON (Contract 01) after analysis completes.

    WHY STORE JSON IN A TEXT COLUMN:
      ParsedPaper is a complex nested object. Storing it as serialised JSON
      in a single Text column is simpler than designing 5+ normalised tables
      for an MVP. model_dump_json() and model_validate_json() handle the
      serialisation/deserialisation automatically.
    """
    __tablename__ = "documents"

    id = Column(String, primary_key=True)       # = doc_id (e.g. "3f2a91bc")
    filename = Column(String)                    # original PDF filename
    upload_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="uploaded")  # uploaded|processing|done|error|success|partial
    parsed_json = Column(Text, nullable=True)    # stores full ParsedPaper JSON string


class CitationCacheRecord(Base):
    """
    Cache table for resolved citation metadata.
    Prevents re-fetching the same paper from Semantic Scholar/arXiv
    if it appears in multiple documents.

    NOTE: Not fully used in MVP — resolution results are cached in-memory
    in main.py's _member2_cache dict. This table is here for production scale-up.

    title_hash: md5 of the normalised title string — used as a fast lookup key
    """
    __tablename__ = "citation_cache"

    title_hash = Column(String, primary_key=True)  # md5 of normalised title
    title = Column(String)
    abstract = Column(Text)
    doi = Column(String, nullable=True)
    year = Column(String, nullable=True)
    citation_count = Column(String, nullable=True)


# Create all tables on first run (safe to call multiple times — DDL is idempotent)
Base.metadata.create_all(bind=engine)


# ── Core Document Helpers ─────────────────────────────────────────────────────

def insert_document(doc_id: str, filename: str) -> None:
    """
    Create a new document row when a PDF is first uploaded.
    Called immediately after the file is saved to disk in POST /upload-pdf.
    Status starts as "uploaded".
    """
    db = SessionLocal()
    try:
        record = DocumentRecord(id=doc_id, filename=filename, status="uploaded")
        db.add(record)
        db.commit()
    finally:
        db.close()  # always close to return connection to pool


def update_document_status(doc_id: str, status: str) -> None:
    """
    Update the processing status for a document.
    Called at key lifecycle transitions:
      - "processing" — when /analyze starts
      - "success"/"partial"/"failed" — set automatically by save_parsed_paper()

    WHY SEPARATE FROM save_parsed_paper:
      We update status to "processing" BEFORE the slow parsing starts so the
      frontend's polling (/status) sees the transition immediately.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            record.status = status
            db.commit()
    finally:
        db.close()


def save_parsed_paper(doc_id: str, paper: ParsedPaper) -> None:
    """
    Serialises the full ParsedPaper Pydantic model to JSON and stores it
    in the `parsed_json` column. Also updates the status from the paper itself.

    WHY model_dump_json():
      Pydantic's built-in serialiser handles nested objects, Optional fields,
      and list types correctly. Using json.dumps(paper.dict()) would work too
      but model_dump_json() is the modern Pydantic v2 approach.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            record.parsed_json = paper.model_dump_json()  # → compact JSON string
            record.status = paper.processing_status       # "success", "partial", or "failed"
            db.commit()
    finally:
        db.close()


def get_parsed_paper(doc_id: str) -> ParsedPaper | None:
    """
    Retrieves and deserialises a stored ParsedPaper from the database.
    Returns None if the document doesn't exist or hasn't been parsed yet.

    model_validate_json() reconstructs the full Pydantic object with type
    validation — so the caller always gets a properly typed ParsedPaper.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            return ParsedPaper.model_validate_json(record.parsed_json)
        return None
    finally:
        db.close()


def get_document_status(doc_id: str) -> str | None:
    """
    Returns just the status string for a document.
    Used by GET /status endpoint for frontend polling.
    Returns None if the doc_id doesn't exist (signals 404 to the endpoint).
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        return record.status if record else None
    finally:
        db.close()


# =============================================================================
# Member 2 Storage Helpers — for Verification and Roadmap results
# These piggyback on the existing `parsed_json` column by merging JSON dicts.
# In production: create dedicated verification_results and roadmap tables.
# =============================================================================

def save_resolved_citations(doc_id: str, citations_json: str) -> None:
    """
    Save resolved citations JSON to database by merging into parsed_json.
    WHY: Avoids creating a new DB column for MVP. The parsed_json column
    holds whatever dict we merge into it.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            # Load existing JSON, merge in the new key, save back
            existing = json.loads(record.parsed_json) if record.parsed_json else {}
            existing["resolved_citations"] = json.loads(citations_json)
            record.parsed_json = json.dumps(existing)
            db.commit()
    finally:
        db.close()


def save_verification_report(doc_id: str, verification_json: str) -> None:
    """
    Save verification report JSON to database by merging into parsed_json.
    Same pattern as save_resolved_citations — merges into existing JSON blob.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            existing = json.loads(record.parsed_json) if record.parsed_json else {}
            existing["verification_report"] = json.loads(verification_json)
            record.parsed_json = json.dumps(existing)
            db.commit()
    finally:
        db.close()


def save_roadmap_response(doc_id: str, roadmap_json: str) -> None:
    """
    Save roadmap response JSON to database by merging into parsed_json.
    Same pattern — roadmap is stored under the "roadmap" key in the blob.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            existing = json.loads(record.parsed_json) if record.parsed_json else {}
            existing["roadmap"] = json.loads(roadmap_json)
            record.parsed_json = json.dumps(existing)
            db.commit()
    finally:
        db.close()


def get_resolved_citations(doc_id: str) -> dict | None:
    """
    Retrieve resolved citations from the database blob.
    Returns the "resolved_citations" sub-dict or None if not found.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            data = json.loads(record.parsed_json)
            return data.get("resolved_citations")
        return None
    finally:
        db.close()


def get_verification_report(doc_id: str) -> dict | None:
    """
    Retrieve verification report from the database blob.
    Returns the "verification_report" sub-dict or None if not found.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            data = json.loads(record.parsed_json)
            return data.get("verification_report")
        return None
    finally:
        db.close()


def get_roadmap_response(doc_id: str) -> dict | None:
    """
    Retrieve roadmap response from the database blob.
    Returns the "roadmap" sub-dict or None if not found.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            data = json.loads(record.parsed_json)
            return data.get("roadmap")
        return None
    finally:
        db.close()


def get_full_report(doc_id: str) -> dict | None:
    """
    Retrieve the entire stored JSON blob for a document.
    Includes parsed paper data + any merged verification/roadmap data.
    Used for debugging and as a fallback when individual keys aren't found.
    """
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            return json.loads(record.parsed_json)
        return None
    finally:
        db.close()