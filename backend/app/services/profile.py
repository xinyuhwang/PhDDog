from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User, UserProfile
from app.ingest.pdf import extract_pdf
from app.llm import get_llm
from app.llm.schemas import StructuredProfile
from app.services.jobs import enqueue
from app.storage.local import save_bytes, sha256


def active_profile(db: Session, user: User) -> UserProfile | None:
    return db.scalar(
        select(UserProfile).where(UserProfile.user_id == user.id, UserProfile.is_active).order_by(UserProfile.version.desc())
    )


def structured(profile: UserProfile | None) -> StructuredProfile:
    return StructuredProfile.model_validate(profile.structured_profile) if profile and profile.structured_profile else StructuredProfile()


def _new_version(db: Session, user: User, **changes) -> UserProfile:
    """Every change creates a new profile version so screening results stay tied to what was screened."""
    current = active_profile(db, user)
    fields = {
        "resume_file_path": current.resume_file_path if current else None,
        "resume_text": current.resume_text if current else None,
        "research_statement": current.research_statement if current else None,
        "keywords": current.keywords if current else [],
    } | changes
    if current:
        current.is_active = False
    structured_profile = get_llm().structure_resume(fields["resume_text"] or "", fields["research_statement"])
    profile = UserProfile(
        user_id=user.id, version=(current.version + 1) if current else 1, is_active=True,
        structured_profile=structured_profile.model_dump(), **fields,
    )
    db.add(profile)
    db.flush()
    # Screening results belong to a profile version, so every new version re-screens everyone.
    enqueue(db, "screen_all", user_id=user.id)
    db.commit()
    return profile


def upload_resume(db: Session, user: User, content: bytes, filename: str) -> UserProfile:
    path = save_bytes(content, "resumes", f"{sha256(content)}.pdf")
    text = extract_pdf(content).text
    return _new_version(db, user, resume_file_path=path, resume_text=text)


def update_profile(db: Session, user: User, research_statement: str | None, keywords: list[str]) -> UserProfile:
    return _new_version(db, user, research_statement=research_statement, keywords=keywords)
