import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser, get_professor
from app.api.schemas import (
    BulkIn,
    HomepageIn,
    ParseIn,
    ProfessorDetail,
    ProfessorPatch,
    ProfessorSummary,
    ScreenOut,
)
from app.db.models import Professor, School
from app.llm.schemas import ParsedEntry
from app.services import professors as svc
from app.services.profile import active_profile
from app.services.screen import latest_results, request_screen

router = APIRouter(prefix="/professors", tags=["professors"])
EDITABLE_EXTRACTED = set(svc.EXTRACTED_FIELDS)


def _summary(prof: Professor, screen) -> dict:
    data = ProfessorSummary.model_validate(
        {**{c: getattr(prof, c) for c in ProfessorSummary.model_fields if hasattr(prof, c)}, "school_name": prof.school.name}
    ).model_dump()
    data["screen"] = ScreenOut.model_validate(screen).model_dump() if screen else None
    return data


@router.post("/parse", response_model=list[ParsedEntry])
def parse(body: ParseIn, db: DB, user: CurrentUser):
    """Preview how the free-form text was read. Nothing is saved."""
    return svc.parse_input(db, user, body.text)


@router.post("/bulk", response_model=list[ProfessorSummary])
def bulk_add(body: BulkIn, db: DB, user: CurrentUser):
    return [_summary(p, None) for p in svc.add_professors(db, user, body.entries)]


@router.get("", response_model=list[ProfessorSummary])
def list_professors(db: DB, user: CurrentUser):
    profs = db.scalars(
        select(Professor).join(School).where(School.user_id == user.id)
        .options(selectinload(Professor.school)).order_by(Professor.created_at)
    ).all()
    results = latest_results(db, active_profile(db, user))
    return [_summary(p, results.get(p.id)) for p in profs]


@router.post("/screen", status_code=202)
def screen(db: DB, user: CurrentUser):
    if active_profile(db, user) is None:
        raise HTTPException(400, "Add your resume or a research statement on My profile first, so there is something to compare against.")
    request_screen(db, user)
    return {"queued": True}


@router.get("/{professor_id}", response_model=ProfessorDetail)
def get_detail(professor_id: uuid.UUID, db: DB, user: CurrentUser):
    prof = get_professor(db, user, professor_id)
    screen = latest_results(db, active_profile(db, user)).get(prof.id)
    data = _summary(prof, screen)
    data.update({c: getattr(prof, c) for c in ProfessorDetail.model_fields if c not in data and hasattr(prof, c)})
    data["candidates"] = prof.candidates
    data["pages"] = [
        {"url": p.final_url or p.url, "kind": p.kind, "fetch_status": p.fetch_status, "error": p.error,
         "fetched_at": p.fetched_at}
        for p in prof.source_pages
    ]
    return data


@router.patch("/{professor_id}", response_model=ProfessorSummary)
def patch(professor_id: uuid.UUID, body: ProfessorPatch, db: DB, user: CurrentUser):
    prof = get_professor(db, user, professor_id)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(prof, field, value)
    edited = [f for f in changes if f in EDITABLE_EXTRACTED]
    if edited:
        prof.user_overrides = sorted(set(prof.user_overrides) | set(edited))
    if "name" in changes:
        prof.normalized_name = svc.normalize_name(prof.name)
    db.commit()
    return _summary(prof, latest_results(db, active_profile(db, user)).get(prof.id))


@router.delete("/{professor_id}", status_code=204)
def delete(professor_id: uuid.UUID, db: DB, user: CurrentUser):
    db.delete(get_professor(db, user, professor_id))
    db.commit()


@router.post("/{professor_id}/homepage", status_code=202)
def set_homepage(professor_id: uuid.UUID, body: HomepageIn, db: DB, user: CurrentUser):
    svc.set_homepage(db, get_professor(db, user, professor_id), body.url.strip())
    return {"queued": True}


@router.post("/{professor_id}/refresh", status_code=202)
def refresh(professor_id: uuid.UUID, db: DB, user: CurrentUser):
    svc.request_refresh(db, get_professor(db, user, professor_id))
    return {"queued": True}
