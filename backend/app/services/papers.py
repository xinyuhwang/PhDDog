"""Stage ③ Deep-dive: paper intake, summaries and connection points (docs/DESIGN.md §4.3)."""

import re
import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ConnectionPoint, Paper, Professor, User
from app.ingest.paper_sources import resolve_url
from app.ingest.pdf import extract_pdf
from app.llm import get_llm
from app.llm.schemas import PaperSummary
from app.services.jobs import enqueue, handler
from app.services.profile import active_profile, structured
from app.storage.local import save_bytes, sha256


def norm_title(title: str | None) -> str | None:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() if title else None


def year_warning(paper: Paper) -> bool:
    window = get_settings().paper_year_window
    return bool(paper.year and paper.year < date.today().year - window + 1)


def _find_duplicate(db: Session, paper: Paper) -> Paper | None:
    q = select(Paper).where(Paper.professor_id == paper.professor_id, Paper.id != paper.id)
    if paper.doi:
        if dup := db.scalar(q.where(Paper.doi == paper.doi)):
            return dup
    if paper.norm_title:
        return db.scalar(q.where(Paper.norm_title == paper.norm_title, Paper.year == paper.year))
    return None


# --- intake ----------------------------------------------------------------------------


def add_pdf(db: Session, prof: Professor, content: bytes) -> Paper:
    digest = sha256(content)
    if dup := db.scalar(select(Paper).where(Paper.professor_id == prof.id, Paper.sha256 == digest)):
        return dup
    pdf = extract_pdf(content)
    paper = Paper(
        professor_id=prof.id, source_type="pdf", sha256=digest, title=pdf.title, norm_title=norm_title(pdf.title),
        doi=pdf.doi, year=pdf.year, full_text=pdf.text,
        file_path=save_bytes(content, "papers", str(prof.id), f"{digest}.pdf"),
        text_status="full" if len(pdf.text) >= 3000 else ("abstract_only" if pdf.text.strip() else "failed"),
    )
    db.add(paper)
    db.flush()
    if dup := _find_duplicate(db, paper):
        db.delete(paper)
        db.commit()
        return dup
    enqueue(db, "summarize_paper", paper_id=paper.id)
    db.commit()
    return paper


def add_url(db: Session, prof: Professor, url: str) -> Paper:
    paper = Paper(professor_id=prof.id, source_type="url", source_url=url, text_status="pending")
    db.add(paper)
    db.flush()
    enqueue(db, "ingest_paper_url", paper_id=paper.id)
    db.commit()
    return paper


@handler("ingest_paper_url")
def ingest_paper_url(db: Session, payload: dict) -> None:
    paper = db.get(Paper, uuid.UUID(payload["paper_id"]))
    meta = resolve_url(paper.source_url)
    paper.title, paper.norm_title = meta.title, norm_title(meta.title)
    paper.authors, paper.year, paper.venue, paper.doi = meta.authors, meta.year, meta.venue, meta.doi
    paper.abstract, paper.full_text, paper.text_status = meta.abstract, meta.full_text, meta.text_status
    paper.error = "; ".join(meta.notes) or None
    if meta.pdf_bytes:
        paper.sha256 = sha256(meta.pdf_bytes)
        paper.file_path = save_bytes(meta.pdf_bytes, "papers", str(paper.professor_id), f"{paper.sha256}.pdf")
    db.flush()
    if dup := _find_duplicate(db, paper):
        db.delete(paper)
        return
    if paper.text_status != "failed":
        enqueue(db, "summarize_paper", paper_id=paper.id)


@handler("summarize_paper")
def summarize_paper(db: Session, payload: dict) -> None:
    paper = db.get(Paper, uuid.UUID(payload["paper_id"]))
    text = paper.full_text or paper.abstract or ""
    paper.summary = get_llm().summarize_paper(paper.title, text).model_dump()


# --- analysis ----------------------------------------------------------------------------


def request_analysis(db: Session, user: User, prof: Professor) -> None:
    enqueue(db, "find_connections", professor_id=prof.id, user_id=user.id)
    db.commit()


@handler("find_connections")
def find_connections(db: Session, payload: dict) -> None:
    prof = db.get(Professor, uuid.UUID(payload["professor_id"]))
    user = db.get(User, uuid.UUID(payload["user_id"]))
    profile = active_profile(db, user)
    if profile is None:
        raise ValueError("Upload a resume first")
    papers = [p for p in prof.papers if p.summary]
    if not papers:
        raise ValueError("No summarized papers yet")
    results = get_llm().find_connections(
        [(p.title or "", p.full_text or p.abstract or "", PaperSummary.model_validate(p.summary)) for p in papers],
        structured(profile), profile.resume_text or "",
    )
    db.execute(delete(ConnectionPoint).where(ConnectionPoint.professor_id == prof.id))
    for i, c in results:
        db.add(ConnectionPoint(
            professor_id=prof.id, paper_id=papers[i].id, profile_version=profile.version, **c.model_dump(),
        ))
    if prof.status in ("added", "resolved", "screened", "shortlisted"):
        prof.status = "analyzed"
