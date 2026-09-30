"""Stage ② Screen (docs/DESIGN.md §4.2)."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Professor, School, ScreenResult, User, UserProfile
from app.llm import get_llm
from app.services.jobs import enqueue, handler
from app.services.profile import active_profile, structured


def request_screen(db: Session, user: User) -> None:
    enqueue(db, "screen_all", user_id=user.id)
    db.commit()


@handler("screen_all")
def screen_all(db: Session, payload: dict) -> None:
    user = db.get(User, uuid.UUID(payload["user_id"]))
    profile = active_profile(db, user)
    if profile is None:
        raise ValueError("Upload a resume or add a research statement first")
    for prof in db.scalars(select(Professor).join(School).where(School.user_id == user.id)):
        screen_one(db, profile, prof)


def screen_one(db: Session, profile: UserProfile, prof: Professor) -> ScreenResult | None:
    if not prof.stated_interests:
        return None
    llm = get_llm()
    out = llm.screen_professor(structured(profile), profile.keywords, profile.research_statement, prof.stated_interests)
    db.execute(
        delete(ScreenResult).where(ScreenResult.professor_id == prof.id, ScreenResult.profile_version == profile.version)
    )
    result = ScreenResult(
        professor_id=prof.id, profile_version=profile.version, score=out.score, label=out.label,
        reason=out.reason, model=llm.name,
    )
    db.add(result)
    if prof.status in ("added", "resolved"):
        prof.status = "screened"
    return result


def latest_results(db: Session, profile: UserProfile | None) -> dict:
    if profile is None:
        return {}
    rows = db.scalars(select(ScreenResult).where(ScreenResult.profile_version == profile.version))
    return {r.professor_id: r for r in rows}
