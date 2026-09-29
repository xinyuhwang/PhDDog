"""DB-backed job queue. The worker process (app/worker.py) runs queued jobs."""

import logging
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job

log = logging.getLogger(__name__)
MAX_ATTEMPTS = 2

Handler = Callable[[Session, dict], None]
_handlers: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _handlers[kind] = fn
        return fn

    return register


def enqueue(db: Session, kind: str, **payload) -> Job:
    job = Job(kind=kind, payload={k: str(v) if isinstance(v, uuid.UUID) else v for k, v in payload.items()})
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session) -> Job | None:
    job = db.scalar(
        select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1).with_for_update(skip_locked=True)
    )
    if job:
        job.status, job.started_at, job.attempts = "running", datetime.now(UTC), job.attempts + 1
        db.commit()
    return job


def run(db: Session, job: Job) -> None:
    # Import here so every @handler is registered before lookup.
    from app.services import papers, professors, screen  # noqa: F401

    try:
        _handlers[job.kind](db, job.payload)
        db.commit()
        job.status, job.error = "done", None
    except Exception as e:  # noqa: BLE001 - record any failure on the job
        db.rollback()
        log.exception("job %s (%s) failed", job.id, job.kind)
        job = db.get(Job, job.id)
        job.error = f"{e}\n{traceback.format_exc(limit=3)}"
        job.status = "queued" if job.attempts < MAX_ATTEMPTS else "failed"
    job.finished_at = datetime.now(UTC)
    db.commit()


def run_pending(db: Session, limit: int = 100) -> int:
    """Run queued jobs inline (used by tests and scripts)."""
    count = 0
    while count < limit and (job := claim_next(db)):
        run(db, job)
        count += 1
    return count
