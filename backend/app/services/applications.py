"""PhD application tracker: per-program checklist with due dates counted back from the deadline."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Application, ApplicationStep, Professor, User

# (label, days before the deadline it should be done; None = due with the deadline)
DEFAULT_STEPS: list[tuple[str, int | None]] = [
    ("Create an account on the application portal", 45),
    ("Ask recommenders for letters (give them 4–6 weeks)", 42),
    ("Pick the faculty to name in the application", 30),
    ("Send official test scores (TOEFL/IELTS, GRE if required)", 21),
    ("Draft statement of purpose", 21),
    ("Update CV", 14),
    ("Finalize statement of purpose (tailored to this program)", 10),
    ("Upload transcripts", 7),
    ("Confirm all letters are submitted", 3),
    ("Pay the fee or request a waiver", 2),
    ("Submit the application", 0),
]
URGENT_DAYS = 7


def create(db: Session, user: User, school_id, program: str, **fields) -> Application:
    app = Application(user_id=user.id, school_id=school_id, program=program, **fields)
    db.add(app)
    db.flush()
    for i, (label, before) in enumerate(DEFAULT_STEPS):
        due = app.deadline - timedelta(days=before) if app.deadline and before is not None else None
        db.add(ApplicationStep(application_id=app.id, label=label, position=i, due_date=due))
    db.commit()
    db.refresh(app)
    return app


def set_deadline(app: Application, deadline: date | None) -> None:
    """Moving the deadline moves the default steps' due dates with it."""
    old = app.deadline
    app.deadline = deadline
    defaults = {label: before for label, before in DEFAULT_STEPS}
    for step in app.steps:
        before = defaults.get(step.label)
        if before is None or step.done:
            continue
        if old is None or step.due_date is None or step.due_date == old - timedelta(days=before):
            step.due_date = deadline - timedelta(days=before) if deadline else None


def due(step: ApplicationStep, app: Application) -> date | None:
    return step.due_date or app.deadline


def toggle(step: ApplicationStep, done: bool) -> None:
    step.done = done
    step.done_at = datetime.now(UTC) if done else None
    app = step.application
    if done and app.status == "planning":
        app.status = "in_progress"


@dataclass
class Progress:
    done: int
    total: int
    remaining: int
    overdue: int
    due_soon: int  # not done, due within URGENT_DAYS
    days_left: int | None
    next_step: ApplicationStep | None


def progress(app: Application, today: date | None = None) -> Progress:
    today = today or date.today()
    open_steps = [s for s in app.steps if not s.done]
    dues = [(due(s, app), s) for s in open_steps]
    overdue = sum(1 for d, _ in dues if d and d < today)
    soon = sum(1 for d, _ in dues if d and today <= d <= today + timedelta(days=URGENT_DAYS))
    ordered = sorted(dues, key=lambda x: (x[0] or date.max, x[1].position))
    return Progress(
        done=len(app.steps) - len(open_steps), total=len(app.steps), remaining=len(open_steps), overdue=overdue,
        due_soon=soon, days_left=(app.deadline - today).days if app.deadline else None,
        next_step=ordered[0][1] if ordered else None,
    )


ACTIVE = ("planning", "in_progress")


def todo(db: Session, user: User, today: date | None = None, limit: int = 15) -> list[tuple[ApplicationStep, Application, date | None]]:
    """Unfinished steps across active applications, most urgent first."""
    today = today or date.today()
    apps = db.scalars(
        select(Application).where(Application.user_id == user.id, Application.status.in_(ACTIVE))
        .options(selectinload(Application.steps), selectinload(Application.school))
    ).all()
    items = [(s, a, due(s, a)) for a in apps for s in a.steps if not s.done]
    items.sort(key=lambda x: (x[2] or date.max, x[1].deadline or date.max, x[0].position))
    return items[:limit]


def pinned_faculty(db: Session, app: Application) -> list[Professor]:
    """Professors at this school the user pinned (or got further with): candidates to name in the application."""
    return db.scalars(
        select(Professor).where(
            Professor.school_id == app.school_id,
            Professor.status.in_(["shortlisted", "analyzed", "drafted", "contacted", "replied"]),
        ).order_by(Professor.name)
    ).all()
