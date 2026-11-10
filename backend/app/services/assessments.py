"""Admission evaluation on My profile (docs/DESIGN.md §4.11).

One evaluation per active application at each selected school. Ratings come from Claude only;
the offline rules never produce them. Every reason must carry checkable evidence.
"""

import hashlib
import json
import re
import uuid
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AdmissionAssessment, Application, Professor, School, User, UserProfile
from app.llm import get_llm
from app.llm.schemas import AssessmentOut, ProgramContext
from app.services.jobs import enqueue, handler
from app.services.profile import active_profile, structured

# Providers that can make a judgment call. The fake provider (and Ollama, which extends it) can't.
JUDGMENT_PROVIDERS = {"claude"}


def can_run() -> bool:
    return get_llm().name in JUDGMENT_PROVIDERS


def _squash(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def materials(profile: UserProfile) -> str:
    """Everything the user uploaded or wrote; the pool that profile evidence must quote."""
    return " \n ".join(t for t in (profile.resume_text, profile.research_statement, profile.project_notes) if t)


def evaluated_programs(db: Session, user: User) -> list[tuple[School, Application | None]]:
    """Selected schools with each application still in play; a school with none is evaluated on its own."""
    schools = db.scalars(select(School).where(School.user_id == user.id, School.is_target).order_by(School.name)).all()
    out = []
    for s in schools:
        apps = db.scalars(
            select(Application).where(Application.school_id == s.id, Application.decision != "drop")
            .order_by(Application.deadline.nulls_last(), Application.program)
        ).all()
        out.extend((s, a) for a in apps) if apps else out.append((s, None))
    return out


def _faculty(db: Session, school: School) -> list[Professor]:
    return db.scalars(select(Professor).where(Professor.school_id == school.id).order_by(Professor.name)).all()


def check_reasons(db: Session, profile: UserProfile, school: School, out: AssessmentOut) -> list[str]:
    """Return the problems with an evaluation's evidence; empty if every reason checks out."""
    pool = _squash(materials(profile))
    names = [_squash(p.name) for p in _faculty(db, school)]
    problems = []
    if not 1 <= len(out.reasons) <= 5:
        problems.append("give 1–5 reasons")
    for i, r in enumerate(out.reasons, 1):
        ev = _squash(r.evidence)
        if r.kind == "profile":
            if len(ev) < 15 or ev not in pool:
                problems.append(f"#{i} quote of your materials not found: {r.evidence[:60]!r}")
        elif r.kind == "faculty":
            if not any(n and n in ev for n in names):
                problems.append(f"#{i} names no professor saved for {school.name}")
        elif not (r.source_url or "").startswith(("http://", "https://")):
            problems.append(f"#{i} ({r.kind}) needs a source_url")
    return problems


def save(db: Session, user: User, profile: UserProfile, school: School, app: Application | None,
         out: AssessmentOut, assessed_by: str) -> AdmissionAssessment:
    key = inputs_key(context(db, school, app))  # before the row exists, so no half-filled row is flushed
    row = db.scalar(select(AdmissionAssessment).where(
        AdmissionAssessment.school_id == school.id,
        AdmissionAssessment.application_id == app.id if app else AdmissionAssessment.application_id.is_(None),
    ))
    if row is None:
        row = AdmissionAssessment(user_id=user.id, school_id=school.id, application_id=app.id if app else None)
        db.add(row)
    row.rating, row.summary, row.gap, row.action = out.rating, out.summary, out.gap, out.action
    row.reasons = [r.model_dump() for r in out.reasons]
    row.profile_version, row.assessed_by = profile.version, assessed_by
    row.inputs_key = key
    db.flush()
    return row


def import_assessment(db: Session, user: User, school: School, app: Application | None,
                      out: AssessmentOut, assessed_by: str) -> AdmissionAssessment:
    """Store an evaluation written outside the pipeline (e.g. by Claude in a session). Raises ValueError."""
    profile = active_profile(db, user)
    if profile is None:
        raise ValueError("Upload a resume first")
    if problems := check_reasons(db, profile, school, out):
        raise ValueError("; ".join(problems))
    row = save(db, user, profile, school, app, out, assessed_by)
    db.commit()
    return row


def request_run(db: Session, user: User) -> None:
    if not can_run():
        raise PermissionError("Evaluating admission chances needs Claude (LLM_PROVIDER=claude).")
    if active_profile(db, user) is None:
        raise ValueError("Upload a resume first")
    if not evaluated_programs(db, user):
        raise ValueError("Select at least one school first")
    enqueue(db, "assess_admission", user_id=user.id)
    db.commit()


def context(db: Session, school: School, app: Application | None) -> ProgramContext:
    funding = " ".join(t for t in (school.funding_level and f"Level: {school.funding_level}.", school.funding_note,
                                   school.funding_guarantee and f"Guarantee: {school.funding_guarantee}") if t)
    return ProgramContext(
        school=school.name, program=app.program if app else "PhD (no application saved)",
        requirements=app.requirements if app else {}, notes=app.notes if app else None,
        funding=funding or None, admit_note=school.admit_note,
        faculty=[f"{p.name} ({p.recruiting_status}, {p.contact_policy})" for p in _faculty(db, school)],
    )


@handler("assess_admission")
def assess_admission(db: Session, payload: dict) -> None:
    user = db.get(User, uuid.UUID(payload["user_id"]))
    profile = active_profile(db, user)
    pairs = evaluated_programs(db, user)
    llm = get_llm()
    results = llm.assess_admission(structured(profile), materials(profile), [context(db, s, a) for s, a in pairs])
    for (school, app), out in zip(pairs, results, strict=True):
        # Keep only the reasons whose evidence checks out; skip the program if none do.
        out.reasons = [r for r in out.reasons if not check_reasons(
            db, profile, school, AssessmentOut(rating=out.rating, summary="", reasons=[r]))]
        if out.reasons:
            save(db, user, profile, school, app, out, llm.name)


def inputs_key(ctx: ProgramContext) -> str:
    return hashlib.sha256(json.dumps(asdict(ctx), sort_keys=True, default=str).encode()).hexdigest()[:16]


def stale_reasons(db: Session, row: AdmissionAssessment, profile: UserProfile | None,
                  school: School, app: Application | None) -> list[str]:
    reasons = []
    if profile is None or profile.version != row.profile_version:
        reasons.append("your resume or materials changed")
    if inputs_key(context(db, school, app)) != row.inputs_key:
        reasons.append("the school's funding, admit notes, faculty or requirements changed")
    return reasons
