import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.api.schemas import JobOut, SchoolConfirmIn, SchoolOut
from app.config import get_settings
from app.db.models import Job, Professor, School
from app.llm import get_llm
from app.services.schools import confirm_school

router = APIRouter(tags=["meta"])


@router.get("/health")
def health():
    s = get_settings()
    return {"ok": True, "llm_provider": get_llm().name, "target_cycle": s.target_cycle}


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(db: DB, active: bool = True):
    q = select(Job).order_by(Job.created_at.desc()).limit(50)
    if active:
        q = q.where(Job.status.in_(["queued", "running", "failed"]))
    return db.scalars(q).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: DB):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404)
    return job


@router.get("/schools", response_model=list[SchoolOut])
def list_schools(db: DB, user: CurrentUser):
    counts = dict(db.execute(select(Professor.school_id, func.count()).group_by(Professor.school_id)).all())
    schools = db.scalars(select(School).where(School.user_id == user.id).order_by(School.name)).all()
    return [SchoolOut.model_validate(s).model_copy(update={"professor_count": counts.get(s.id, 0)}) for s in schools]


@router.post("/schools/{school_id}/confirm", response_model=SchoolOut)
def confirm(school_id: uuid.UUID, body: SchoolConfirmIn, db: DB, user: CurrentUser):
    """Say which school this is. Merges into an existing school if the name matches one."""
    school = db.get(School, school_id)
    if school is None or school.user_id != user.id:
        raise HTTPException(404)
    try:
        return confirm_school(db, user, school, body.name, body.primary_domain, body.aliases)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
