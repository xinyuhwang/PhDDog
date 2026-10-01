import uuid
from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB, CurrentUser
from app.db.models import Application, ApplicationStep, School
from app.services import applications as svc

router = APIRouter(tags=["applications"])
STATUSES = ("planning", "in_progress", "submitted", "interview", "admitted", "waitlisted", "rejected", "withdrawn")


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    label: str
    position: int
    done: bool
    done_at: datetime | None
    due_date: date | None
    effective_due: date | None = None


class FacultyRef(BaseModel):
    id: uuid.UUID
    name: str
    recruiting_status: str
    contact_policy: str


class ApplicationOut(BaseModel):
    id: uuid.UUID
    school_id: uuid.UUID
    school_name: str
    program: str
    deadline: date | None
    deadline_text: str | None
    deadline_cycle: str | None
    deadline_source_url: str | None
    apply_url: str | None
    requirements: dict
    status: str
    notes: str | None
    steps: list[StepOut]
    done: int
    total: int
    remaining: int
    overdue: int
    due_soon: int
    days_left: int | None
    next_step: StepOut | None
    faculty: list[FacultyRef]


class ApplicationIn(BaseModel):
    school_id: uuid.UUID
    program: str
    deadline: date | None = None
    deadline_text: str | None = None
    deadline_cycle: str | None = None
    deadline_source_url: str | None = None
    apply_url: str | None = None
    requirements: dict = {}
    notes: str | None = None


class ApplicationPatch(BaseModel):
    program: str | None = None
    deadline: date | None = None
    apply_url: str | None = None
    status: str | None = None
    notes: str | None = None
    requirements: dict | None = None


class StepIn(BaseModel):
    label: str
    due_date: date | None = None


class StepPatch(BaseModel):
    label: str | None = None
    done: bool | None = None
    due_date: date | None = None


class TodoOut(BaseModel):
    step: StepOut
    application_id: uuid.UUID
    school_name: str
    program: str
    due: date | None
    days_until: int | None


def _step(s: ApplicationStep, app: Application) -> StepOut:
    return StepOut.model_validate(s).model_copy(update={"effective_due": svc.due(s, app)})


def _out(db, app: Application) -> ApplicationOut:
    p = svc.progress(app)
    return ApplicationOut(
        id=app.id, school_id=app.school_id, school_name=app.school.name, program=app.program, deadline=app.deadline,
        deadline_text=app.deadline_text, deadline_cycle=app.deadline_cycle, deadline_source_url=app.deadline_source_url,
        apply_url=app.apply_url, requirements=app.requirements or {}, status=app.status, notes=app.notes,
        steps=[_step(s, app) for s in app.steps], done=p.done, total=p.total, remaining=p.remaining,
        overdue=p.overdue, due_soon=p.due_soon, days_left=p.days_left,
        next_step=_step(p.next_step, app) if p.next_step else None,
        faculty=[FacultyRef(id=f.id, name=f.name, recruiting_status=f.recruiting_status, contact_policy=f.contact_policy)
                 for f in svc.pinned_faculty(db, app)],
    )


def _get(db, user, app_id: uuid.UUID) -> Application:
    app = db.get(Application, app_id)
    if app is None or app.user_id != user.id:
        raise HTTPException(404, "Application not found")
    return app


def _get_step(db, user, step_id: uuid.UUID) -> ApplicationStep:
    step = db.get(ApplicationStep, step_id)
    if step is None:
        raise HTTPException(404)
    _get(db, user, step.application_id)
    return step


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(db: DB, user: CurrentUser):
    apps = db.scalars(
        select(Application).where(Application.user_id == user.id)
        .options(selectinload(Application.steps), selectinload(Application.school))
    ).all()
    apps = sorted(apps, key=lambda a: (a.status not in svc.ACTIVE, a.deadline or date.max, a.school.name))
    return [_out(db, a) for a in apps]


@router.get("/applications/todo", response_model=list[TodoOut])
def todo(db: DB, user: CurrentUser, limit: int = 15):
    today = date.today()
    return [
        TodoOut(step=_step(s, a), application_id=a.id, school_name=a.school.name, program=a.program, due=d,
                days_until=(d - today).days if d else None)
        for s, a, d in svc.todo(db, user, limit=limit)
    ]


@router.post("/applications", response_model=ApplicationOut)
def create(body: ApplicationIn, db: DB, user: CurrentUser):
    school = db.get(School, body.school_id)
    if school is None or school.user_id != user.id:
        raise HTTPException(404, "School not found")
    school.is_target = True
    app = svc.create(db, user, **body.model_dump())
    return _out(db, app)


@router.patch("/applications/{app_id}", response_model=ApplicationOut)
def patch(app_id: uuid.UUID, body: ApplicationPatch, db: DB, user: CurrentUser):
    app = _get(db, user, app_id)
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] not in STATUSES:
        raise HTTPException(400, f"status must be one of {', '.join(STATUSES)}")
    if "deadline" in changes:
        svc.set_deadline(app, changes.pop("deadline"))
    for k, v in changes.items():
        setattr(app, k, v)
    db.commit()
    db.refresh(app)
    return _out(db, app)


@router.delete("/applications/{app_id}", status_code=204)
def delete(app_id: uuid.UUID, db: DB, user: CurrentUser):
    db.delete(_get(db, user, app_id))
    db.commit()


@router.post("/applications/{app_id}/steps", response_model=ApplicationOut)
def add_step(app_id: uuid.UUID, body: StepIn, db: DB, user: CurrentUser):
    app = _get(db, user, app_id)
    db.add(ApplicationStep(application_id=app.id, label=body.label.strip(), due_date=body.due_date,
                           position=max((s.position for s in app.steps), default=-1) + 1))
    db.commit()
    db.refresh(app)
    return _out(db, app)


@router.patch("/application-steps/{step_id}", response_model=StepOut)
def patch_step(step_id: uuid.UUID, body: StepPatch, db: DB, user: CurrentUser):
    step = _get_step(db, user, step_id)
    changes = body.model_dump(exclude_unset=True)
    if "done" in changes:
        svc.toggle(step, changes.pop("done"))
    for k, v in changes.items():
        setattr(step, k, v)
    db.commit()
    return _step(step, step.application)


@router.delete("/application-steps/{step_id}", status_code=204)
def delete_step(step_id: uuid.UUID, db: DB, user: CurrentUser):
    db.delete(_get_step(db, user, step_id))
    db.commit()
