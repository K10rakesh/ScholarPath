# backend/database.py
# SQLite database setup and helper functions.

import json
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime, Float
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.schemas import ParsedPaper

# ── Database setup ─────────────────────────────────────────────────────────────

DATABASE_URL = "sqlite:///./backend/scholarpath.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ── Table definitions ──────────────────────────────────────────────────────────

class DocumentRecord(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)       # = doc_id
    filename = Column(String)
    upload_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="uploaded")  # uploaded|processing|done|error
    parsed_json = Column(Text, nullable=True)    # stores full ParsedPaper JSON


class CitationCacheRecord(Base):
    __tablename__ = "citation_cache"

    title_hash = Column(String, primary_key=True)  # md5 of normalised title
    title = Column(String)
    abstract = Column(Text)
    doi = Column(String, nullable=True)
    year = Column(String, nullable=True)
    citation_count = Column(String, nullable=True)


# Create tables on first run
Base.metadata.create_all(bind=engine)


# ── Helper functions ───────────────────────────────────────────────────────────

def insert_document(doc_id: str, filename: str) -> None:
    """Create a new document row when a PDF is first uploaded."""
    db = SessionLocal()
    try:
        record = DocumentRecord(id=doc_id, filename=filename, status="uploaded")
        db.add(record)
        db.commit()
    finally:
        db.close()


def update_document_status(doc_id: str, status: str) -> None:
    """Update processing status: uploaded → processing → done/error."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            record.status = status
            db.commit()
    finally:
        db.close()


def save_parsed_paper(doc_id: str, paper: ParsedPaper) -> None:
    """Serialize ParsedPaper to JSON and store it in the database."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            record.parsed_json = paper.model_dump_json()
            record.status = paper.processing_status
            db.commit()
    finally:
        db.close()


def get_parsed_paper(doc_id: str) -> ParsedPaper | None:
    """Retrieve and deserialize a stored ParsedPaper."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            return ParsedPaper.model_validate_json(record.parsed_json)
        return None
    finally:
        db.close()


def get_document_status(doc_id: str) -> str | None:
    """Get just the status string for a document."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        return record.status if record else None
    finally:
        db.close()


# =============================================================================
# Member 2 Database Helpers - Store verification and roadmap results
# =============================================================================

def save_resolved_citations(doc_id: str, resolved_json: str) -> None:
    """Store resolved citations JSON in the database."""
    db = SessionLocal()
    try:
        # Store in a separate table for citation cache
        from sqlalchemy import text
        # For now, we'll just store as a separate record type
        # In production, you'd create a separate verification_results table
        pass
    finally:
        db.close()


def save_verification_report(doc_id: str, verification_json: str) -> None:
    """Store verification report JSON in the database."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            # Append verification to a separate field or use parsed_json for combined
            # For MVP, we store the verification report in a new column (would need migration)
            pass
    finally:
        db.close()


def save_roadmap_response(doc_id: str, roadmap_json: str) -> None:
    """Store roadmap response JSON in the database."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            pass
    finally:
        db.close()


def get_verification_report(doc_id: str) -> dict | None:
    """Retrieve verification report for a document."""
    # For MVP, this would read from a separate table
    # For now, returns None - in production, add verification_results column
    return None


def get_roadmap_response(doc_id: str) -> dict | None:
    """Retrieve roadmap response for a document."""
    return None


# =============================================================================
# Member 2 - Additional storage helpers
# =============================================================================

def save_resolved_citations(doc_id: str, citations_json: str) -> None:
    """Save resolved citations JSON to database."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            # Store in a separate column or append to parsed_json
            # For simplicity, we'll use a JSON field approach
            import json
            existing = json.loads(record.parsed_json) if record.parsed_json else {}
            existing["resolved_citations"] = json.loads(citations_json)
            record.parsed_json = json.dumps(existing)
            db.commit()
    finally:
        db.close()


def save_verification_report(doc_id: str, verification_json: str) -> None:
    """Save verification report JSON to database."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            import json
            existing = json.loads(record.parsed_json) if record.parsed_json else {}
            existing["verification_report"] = json.loads(verification_json)
            record.parsed_json = json.dumps(existing)
            db.commit()
    finally:
        db.close()


def save_roadmap_response(doc_id: str, roadmap_json: str) -> None:
    """Save roadmap response JSON to database."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record:
            import json
            existing = json.loads(record.parsed_json) if record.parsed_json else {}
            existing["roadmap"] = json.loads(roadmap_json)
            record.parsed_json = json.dumps(existing)
            db.commit()
    finally:
        db.close()


def get_resolved_citations(doc_id: str) -> dict | None:
    """Retrieve resolved citations from storage."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            import json
            data = json.loads(record.parsed_json)
            return data.get("resolved_citations")
        return None
    finally:
        db.close()


def get_verification_report(doc_id: str) -> dict | None:
    """Retrieve verification report from storage."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            import json
            data = json.loads(record.parsed_json)
            return data.get("verification_report")
        return None
    finally:
        db.close()


def get_roadmap_response(doc_id: str) -> dict | None:
    """Retrieve roadmap response from storage."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            import json
            data = json.loads(record.parsed_json)
            return data.get("roadmap")
        return None
    finally:
        db.close()


def get_full_report(doc_id: str) -> dict | None:
    """Retrieve the full combined report (all contracts merged)."""
    db = SessionLocal()
    try:
        record = db.query(DocumentRecord).filter_by(id=doc_id).first()
        if record and record.parsed_json:
            import json
            return json.loads(record.parsed_json)
        return None
    finally:
        db.close()