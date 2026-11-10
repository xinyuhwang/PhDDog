import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.api.schemas import SchoolOut
from app.db.models import AdmissionAssessment, Application, School
from app.llm.schemas import AdmissionRating, AssessmentOut, AssessmentReason
from app.services import assessments as svc
from app.services.profile import active_profile

router = APIRouter(tags=["assessments"])


class AssessmentRow(BaseModel):
    school_id: uuid.UUID
    school_name: str
    application_id: uuid.UUID | None
    program: str | None
    rating: AdmissionRating | None = None  # None = not evaluated yet
    summary: str | None = None
    reasons: list[AssessmentReason] = []
    gap: str | None = None
    action: str | None = None
    assessed_by: str | None = None
    assessed_at: datetime | None = None
    stale: list[str] = []  # why the evaluation may be out of date


class AssessmentsOut(BaseModel):
    can_run: bool  # a provider that can judge admission chances is configured
    has_profile: bool
    rows: list[AssessmentRow]


class AssessmentIn(AssessmentOut):
    school_id: uuid.UUID
    application_id: uuid.UUID | None = None
    assessed_by: str = "claude-session"


class AdmitNoteIn(BaseModel):
    admit_note: str | None


@router.get("/assessments", response_model=AssessmentsOut)
def list_assessments(db: DB, user: CurrentUser):
    """One row per program at each selected school, evaluated or not."""
    profile = active_profile(db, user)
    saved = {(a.school_id, a.application_id): a for a in db.scalars(
        select(AdmissionAssessment).where(AdmissionAssessment.user_id == user.id))}
    rows = []
    for school, app in svc.evaluated_programs(db, user):
        row = AssessmentRow(school_id=school.id, school_name=school.name,
                            application_id=app.id if app else None, program=app.program if app else None)
        if a := saved.get((school.id, app.id if app else None)):
            row = row.model_copy(update={
                "rating": a.rating, "summary": a.summary, "reasons": a.reasons, "gap": a.gap, "action": a.action,
                "assessed_by": a.assessed_by, "assessed_at": a.updated_at,
                "stale": svc.stale_reasons(db, a, profile, school, app),
            })
        rows.append(row)
    return AssessmentsOut(can_run=svc.can_run(), has_profile=profile is not None, rows=rows)


@router.post("/assessments/run", status_code=202)
def run_assessments(db: DB, user: CurrentUser):
    try:
        svc.request_run(db, user)
    except PermissionError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"queued": True}


@router.put("/assessments", response_model=AssessmentRow)
def put_assessment(body: AssessmentIn, db: DB, user: CurrentUser):
    """Store an evaluation written outside the pipeline. Its evidence is checked."""
    school = db.get(School, body.school_id)
    if school is None or school.user_id != user.id:
        raise HTTPException(404, "School not found")
    app = None
    if body.application_id:
        app = db.get(Application, body.application_id)
        if app is None or app.school_id != school.id:
            raise HTTPException(404, "Application not found for this school")
    out = AssessmentOut.model_validate(body.model_dump(include=set(AssessmentOut.model_fields)))
    try:
        a = svc.import_assessment(db, user, school, app, out, body.assessed_by)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return AssessmentRow(
        school_id=school.id, school_name=school.name, application_id=a.application_id,
        program=app.program if app else None, rating=a.rating, summary=a.summary, reasons=a.reasons,
        gap=a.gap, action=a.action, assessed_by=a.assessed_by, assessed_at=a.updated_at,
    )


@router.patch("/schools/{school_id}/admit-note", response_model=SchoolOut)
def set_admit_note(school_id: uuid.UUID, body: AdmitNoteIn, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if school is None or school.user_id != user.id:
        raise HTTPException(404)
    school.admit_note = (body.admit_note or "").strip() or None
    db.commit()
    return school
