import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_professor
from app.api.schemas import DraftEditIn, DraftIn, DraftOut, OutreachOut, OutreachPatch, SendIn, TaskIn, TaskOut, TaskPatch
from app.db.models import EmailDraft, Outreach, OutreachTask, Professor, School
from app.services import outreach as svc

router = APIRouter(tags=["outreach"])


@router.get("/professors/{professor_id}/drafts", response_model=list[DraftOut])
def list_drafts(professor_id: uuid.UUID, db: DB, user: CurrentUser):
    get_professor(db, user, professor_id)
    return db.scalars(
        select(EmailDraft).where(EmailDraft.professor_id == professor_id).order_by(EmailDraft.version.desc())
    ).all()


@router.post("/professors/{professor_id}/drafts", response_model=DraftOut)
def create_draft(professor_id: uuid.UUID, body: DraftIn, db: DB, user: CurrentUser):
    prof = get_professor(db, user, professor_id)
    return svc.generate_draft(db, user, prof, body.connection_point_ids, body.tone, body.ask)


@router.put("/drafts/{draft_id}", response_model=DraftOut)
def edit_draft(draft_id: uuid.UUID, body: DraftEditIn, db: DB, user: CurrentUser):
    base = db.get(EmailDraft, draft_id)
    if base is None:
        raise HTTPException(404)
    prof = get_professor(db, user, base.professor_id)
    return svc.save_edit(db, prof, base, body.subject, body.body)


def _outreach_out(o: Outreach, prof: Professor) -> OutreachOut:
    return OutreachOut.model_validate(o).model_copy(update={"professor_name": prof.name, "school_name": prof.school.name})


@router.post("/professors/{professor_id}/outreach", response_model=OutreachOut)
def mark_sent(professor_id: uuid.UUID, body: SendIn, db: DB, user: CurrentUser):
    prof = get_professor(db, user, professor_id)
    draft = db.get(EmailDraft, body.draft_id)
    if draft is None or draft.professor_id != prof.id:
        raise HTTPException(404, "Draft not found")
    return _outreach_out(svc.mark_sent(db, prof, draft, body.to_address, body.sent_at), prof)


@router.get("/outreach", response_model=list[OutreachOut])
def list_outreach(db: DB, user: CurrentUser, due: bool = False):
    q = (
        select(Outreach, Professor).join(Professor, Professor.id == Outreach.professor_id).join(School)
        .where(School.user_id == user.id).order_by(Outreach.sent_at.desc())
    )
    if due:
        q = q.where(Outreach.follow_up_at <= datetime.now(UTC), Outreach.status.in_(["sent", "no_response"]))
    return [_outreach_out(o, p) for o, p in db.execute(q).all()]


@router.patch("/outreach/{outreach_id}", response_model=OutreachOut)
def patch_outreach(outreach_id: uuid.UUID, body: OutreachPatch, db: DB, user: CurrentUser):
    record = db.get(Outreach, outreach_id)
    if record is None:
        raise HTTPException(404)
    prof = get_professor(db, user, record.professor_id)
    return _outreach_out(svc.update_outreach(db, record, **body.model_dump(exclude_unset=True)), prof)


# --- To-do tasks (shown under the log on the Outreach page) ---------------------------


def _task_out(db, t: OutreachTask) -> TaskOut:
    prof = db.get(Professor, t.professor_id) if t.professor_id else None
    return TaskOut.model_validate(t).model_copy(update={
        "professor_name": prof.name if prof else None, "school_name": prof.school.name if prof else None,
    })


def _get_task(db, user, task_id: uuid.UUID) -> OutreachTask:
    task = db.get(OutreachTask, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/outreach-tasks", response_model=list[TaskOut])
def list_tasks(db: DB, user: CurrentUser, professor_id: uuid.UUID | None = None):
    q = select(OutreachTask).where(OutreachTask.user_id == user.id)
    if professor_id:
        q = q.where(OutreachTask.professor_id == professor_id)
    tasks = db.scalars(q).all()
    # Open first, soonest due first (undated last), then oldest first.
    tasks = sorted(tasks, key=lambda t: (t.done, t.due_date or date.max, t.created_at))
    return [_task_out(db, t) for t in tasks]


@router.post("/outreach-tasks", response_model=TaskOut)
def create_task(body: TaskIn, db: DB, user: CurrentUser):
    if body.professor_id:
        get_professor(db, user, body.professor_id)
    data = body.model_dump()
    task = OutreachTask(user_id=user.id, **data)
    db.add(task)
    db.commit()
    return _task_out(db, task)


@router.patch("/outreach-tasks/{task_id}", response_model=TaskOut)
def patch_task(task_id: uuid.UUID, body: TaskPatch, db: DB, user: CurrentUser):
    task = _get_task(db, user, task_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("professor_id"):
        get_professor(db, user, changes["professor_id"])
    for k, v in changes.items():
        setattr(task, k, v)
    db.commit()
    return _task_out(db, task)


@router.delete("/outreach-tasks/{task_id}", status_code=204)
def delete_task(task_id: uuid.UUID, db: DB, user: CurrentUser):
    db.delete(_get_task(db, user, task_id))
    db.commit()
