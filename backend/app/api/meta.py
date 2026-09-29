import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.api.schemas import JobOut, SchoolIn, SchoolOut
from app.config import get_settings
from app.db.models import Job, School
from app.llm import get_llm

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
    return db.scalars(select(School).where(School.user_id == user.id).order_by(School.name)).all()


@router.patch("/schools/{school_id}", response_model=SchoolOut)
def patch_school(school_id: uuid.UUID, body: SchoolIn, db: DB, user: CurrentUser):
    school = db.get(School, school_id)
    if school is None or school.user_id != user.id:
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(school, k, v)
    db.commit()
    return school
