"""Stage ④ Outreach: email drafts and the outreach log (docs/DESIGN.md §4.4)."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ConnectionPoint, EmailDraft, Outreach, Paper, Professor, User
from app.llm import get_llm
from app.llm.schemas import ConnectionOut
from app.services.profile import active_profile, structured

FOLLOW_UP_DAYS = 14


def _next_version(db: Session, prof: Professor) -> int:
    return (db.scalar(select(func.max(EmailDraft.version)).where(EmailDraft.professor_id == prof.id)) or 0) + 1


def generate_draft(
    db: Session, user: User, prof: Professor, connection_ids: list[uuid.UUID], tone: str, ask: str
) -> EmailDraft:
    profile = active_profile(db, user)
    rows = db.execute(
        select(ConnectionPoint, Paper.title).join(Paper, Paper.id == ConnectionPoint.paper_id).where(
            ConnectionPoint.professor_id == prof.id, ConnectionPoint.id.in_(connection_ids)
        )
    ).all()
    connections = [
        (title or "", ConnectionOut(kind=c.kind, paper_evidence=c.paper_evidence, user_evidence=c.user_evidence,
                                    explanation=c.explanation))
        for c, title in rows
    ]
    llm = get_llm()
    out = llm.draft_email(
        prof.name, prof.title, prof.school.name, connections, structured(profile), user.name or "", tone, ask
    )
    draft = EmailDraft(
        professor_id=prof.id, version=_next_version(db, prof), subject=out.subject, body=out.body, tone=tone, ask=ask,
        connection_point_ids=[str(i) for i in connection_ids], model=llm.name,
    )
    db.add(draft)
    if prof.status in ("added", "resolved", "screened", "shortlisted", "analyzed"):
        prof.status = "drafted"
    db.commit()
    return draft


def save_edit(db: Session, prof: Professor, base: EmailDraft, subject: str, body: str) -> EmailDraft:
    """User edits are saved as a new version; earlier versions are kept."""
    draft = EmailDraft(
        professor_id=prof.id, version=_next_version(db, prof), subject=subject, body=body, tone=base.tone,
        ask=base.ask, connection_point_ids=base.connection_point_ids, model=base.model, edited_by_user=True,
    )
    db.add(draft)
    db.commit()
    return draft


def mark_sent(db: Session, prof: Professor, draft: EmailDraft, to_address: str | None,
              sent_at: datetime | None = None) -> Outreach:
    sent_at = sent_at or datetime.now(UTC)
    record = Outreach(
        professor_id=prof.id, email_draft_id=draft.id, sent_at=sent_at, to_address=to_address or prof.email,
        subject=draft.subject, body=draft.body, status="sent", follow_up_at=sent_at + timedelta(days=FOLLOW_UP_DAYS),
    )
    db.add(record)
    prof.status = "contacted"
    db.commit()
    return record


def update_outreach(db: Session, record: Outreach, **changes) -> Outreach:
    for k, v in changes.items():
        setattr(record, k, v)
    prof = db.get(Professor, record.professor_id)
    if record.status in ("replied", "meeting"):
        prof.status = "replied"
    elif record.status == "declined":
        prof.status = "closed"
    db.commit()
    return record
