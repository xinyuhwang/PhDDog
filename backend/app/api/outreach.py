import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, CurrentUser, get_professor
from app.api.schemas import DraftEditIn, DraftIn, DraftOut, OutreachOut, OutreachPatch, SendIn
from app.db.models import EmailDraft, Outreach, Professor, School
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
