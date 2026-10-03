import uuid

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_professor
from app.api.schemas import ConnectionPointOut, ConnectionSelectIn, PaperOut, PaperUrlIn
from app.db.models import ConnectionPoint, Paper, Professor
from app.llm.schemas import ConnectionOut, PaperSummary
from app.services import papers as svc

router = APIRouter(tags=["papers"])


def _paper_out(p: Paper) -> PaperOut:
    out = PaperOut.model_validate(p)
    out.text_chars = len(p.full_text or "")
    out.year_warning = svc.year_warning(p)
    return out


@router.get("/professors/{professor_id}/papers", response_model=list[PaperOut])
def list_papers(professor_id: uuid.UUID, db: DB, user: CurrentUser):
    prof = get_professor(db, user, professor_id)
    return [_paper_out(p) for p in sorted(prof.papers, key=lambda p: p.created_at)]


@router.post("/professors/{professor_id}/papers/pdf", response_model=PaperOut)
async def upload_pdf(professor_id: uuid.UUID, file: UploadFile, db: DB, user: CurrentUser):
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "Not a PDF file")
    return _paper_out(svc.add_pdf(db, get_professor(db, user, professor_id), content))


@router.post("/professors/{professor_id}/papers/url", response_model=PaperOut)
def add_url(professor_id: uuid.UUID, body: PaperUrlIn, db: DB, user: CurrentUser):
    return _paper_out(svc.add_url(db, get_professor(db, user, professor_id), body.url.strip()))


@router.delete("/papers/{paper_id}", status_code=204)
def delete_paper(paper_id: uuid.UUID, db: DB, user: CurrentUser):
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404)
    get_professor(db, user, paper.professor_id)
    db.delete(paper)
    db.commit()


class AnalysisIn(BaseModel):
    summary: PaperSummary
    connections: list[ConnectionOut]
    analyzed_by: str = "claude-session"


@router.put("/papers/{paper_id}/analysis", response_model=PaperOut)
def put_analysis(paper_id: uuid.UUID, body: AnalysisIn, db: DB, user: CurrentUser):
    """Store a summary + connection points written outside the pipeline. Quotes are verified."""
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404)
    get_professor(db, user, paper.professor_id)
    try:
        svc.import_analysis(db, user, paper, body.summary, body.connections, body.analyzed_by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    db.refresh(paper)
    return _paper_out(paper)


@router.post("/professors/{professor_id}/analyze", status_code=202)
def analyze(professor_id: uuid.UUID, db: DB, user: CurrentUser):
    svc.request_analysis(db, user, get_professor(db, user, professor_id))
    return {"queued": True}


@router.get("/professors/{professor_id}/connections", response_model=list[ConnectionPointOut])
def list_connections(professor_id: uuid.UUID, db: DB, user: CurrentUser):
    get_professor(db, user, professor_id)
    rows = db.execute(
        select(ConnectionPoint, Paper.title).join(Paper, Paper.id == ConnectionPoint.paper_id)
        .where(ConnectionPoint.professor_id == professor_id).order_by(ConnectionPoint.created_at)
    ).all()
    return [ConnectionPointOut.model_validate(c).model_copy(update={"paper_title": t}) for c, t in rows]


@router.patch("/connections/{connection_id}", response_model=ConnectionPointOut)
def select_connection(connection_id: uuid.UUID, body: ConnectionSelectIn, db: DB, user: CurrentUser):
    c = db.get(ConnectionPoint, connection_id)
    if c is None:
        raise HTTPException(404)
    get_professor(db, user, c.professor_id)
    c.selected = body.selected
    db.commit()
    return c
