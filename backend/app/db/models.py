"""Database models. See docs/DESIGN.md §5.

Enum-like columns are plain strings; allowed values are listed in comments and
enforced by the Pydantic schemas at the API boundary.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str | None] = mapped_column(String)


class UserProfile(TimestampMixin, Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer)
    resume_file_path: Mapped[str | None] = mapped_column(String)
    resume_text: Mapped[str | None] = mapped_column(Text)
    research_statement: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list] = mapped_column(JSONB, default=list)
    structured_profile: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class School(TimestampMixin, Base):
    __tablename__ = "schools"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String)
    aliases: Mapped[list] = mapped_column(JSONB, default=list)
    primary_domain: Mapped[str | None] = mapped_column(String)
    website: Mapped[str | None] = mapped_column(String)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Candidate matches to offer when the school couldn't be identified confidently.
    suggestions: Mapped[list] = mapped_column(JSONB, default=list)

    professors: Mapped[list["Professor"]] = relationship(back_populates="school")


class Professor(TimestampMixin, Base):
    __tablename__ = "professors"
    __table_args__ = (UniqueConstraint("school_id", "normalized_name"),)

    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schools.id"))
    name: Mapped[str] = mapped_column(String)
    normalized_name: Mapped[str] = mapped_column(String)
    input_raw: Mapped[str | None] = mapped_column(Text)
    department_raw: Mapped[str | None] = mapped_column(String)
    department: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    homepage_url: Mapped[str | None] = mapped_column(String)
    lab_url: Mapped[str | None] = mapped_column(String)
    scholar_url: Mapped[str | None] = mapped_column(String)  # reference only, never fetched

    # pending | resolved | needs_review | not_found
    resolve_status: Mapped[str] = mapped_column(String, default="pending")
    resolve_confidence: Mapped[float | None] = mapped_column(Float)
    resolve_error: Mapped[str | None] = mapped_column(Text)

    stated_interests: Mapped[str | None] = mapped_column(Text)
    bio_summary: Mapped[str | None] = mapped_column(Text)
    recent_publications: Mapped[list] = mapped_column(JSONB, default=list)

    # explicitly_recruiting | recruits_generally | not_recruiting | unknown
    recruiting_status: Mapped[str] = mapped_column(String, default="unknown")
    recruiting_cycle: Mapped[str | None] = mapped_column(String)
    recruiting_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    # welcomes_email | apply_via_program | do_not_email | unknown
    contact_policy: Mapped[str] = mapped_column(String, default="unknown")
    recruiting_evidence: Mapped[str | None] = mapped_column(Text)
    recruiting_source_url: Mapped[str | None] = mapped_column(String)
    contact_evidence: Mapped[str | None] = mapped_column(Text)
    contact_source_url: Mapped[str | None] = mapped_column(String)

    field_sources: Mapped[dict] = mapped_column(JSONB, default=dict)
    user_overrides: Mapped[list] = mapped_column(JSONB, default=list)  # field names the user edited
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # added | resolved | screened | shortlisted | analyzed | drafted | contacted
    # | replied | closed | dismissed
    status: Mapped[str] = mapped_column(String, default="added")
    notes: Mapped[str | None] = mapped_column(Text)

    school: Mapped[School] = relationship(back_populates="professors")
    candidates: Mapped[list["HomepageCandidate"]] = relationship(
        back_populates="professor", cascade="all, delete-orphan", order_by="HomepageCandidate.rank"
    )
    source_pages: Mapped[list["SourcePage"]] = relationship(
        back_populates="professor", cascade="all, delete-orphan"
    )
    papers: Mapped[list["Paper"]] = relationship(back_populates="professor", cascade="all, delete-orphan")


class HomepageCandidate(TimestampMixin, Base):
    __tablename__ = "homepage_candidates"
    professor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("professors.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String)  # user | search | directory_link
    rank: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)
    chosen: Mapped[bool] = mapped_column(Boolean, default=False)

    professor: Mapped[Professor] = relationship(back_populates="candidates")


class SourcePage(TimestampMixin, Base):
    __tablename__ = "source_pages"
    professor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("professors.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String)
    final_url: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # homepage | subpage | linked_site
    raw_html_path: Mapped[str | None] = mapped_column(String)
    text: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetch_status: Mapped[str] = mapped_column(String, default="pending")  # pending | ok | failed | blocked
    error: Mapped[str | None] = mapped_column(Text)

    professor: Mapped[Professor] = relationship(back_populates="source_pages")


class ScreenResult(TimestampMixin, Base):
    __tablename__ = "screen_results"
    professor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("professors.id", ondelete="CASCADE"))
    profile_version: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String)  # strong | possible | no
    reason: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String)


class Paper(TimestampMixin, Base):
    __tablename__ = "papers"
    professor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("professors.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String)  # pdf | url
    source_url: Mapped[str | None] = mapped_column(String)
    file_path: Mapped[str | None] = mapped_column(String)
    sha256: Mapped[str | None] = mapped_column(String)
    doi: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(Text)
    norm_title: Mapped[str | None] = mapped_column(Text)
    authors: Mapped[list] = mapped_column(JSONB, default=list)
    year: Mapped[int | None] = mapped_column(Integer)
    venue: Mapped[str | None] = mapped_column(String)
    abstract: Mapped[str | None] = mapped_column(Text)
    full_text: Mapped[str | None] = mapped_column(Text)
    # pending | full | abstract_only | failed
    text_status: Mapped[str] = mapped_column(String, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict | None] = mapped_column(JSONB)

    professor: Mapped[Professor] = relationship(back_populates="papers")


class ConnectionPoint(TimestampMixin, Base):
    __tablename__ = "connection_points"
    professor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("professors.id", ondelete="CASCADE"))
    paper_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("papers.id", ondelete="CASCADE"))
    profile_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)  # method_overlap | domain_overlap | future_work_hook
    paper_evidence: Mapped[str] = mapped_column(Text)
    user_evidence: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)


class EmailDraft(TimestampMixin, Base):
    __tablename__ = "email_drafts"
    professor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("professors.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    tone: Mapped[str] = mapped_column(String, default="formal")  # formal | warm
    ask: Mapped[str] = mapped_column(String, default="both")  # phd | ra | both
    connection_point_ids: Mapped[list] = mapped_column(JSONB, default=list)
    model: Mapped[str | None] = mapped_column(String)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False)


class Outreach(TimestampMixin, Base):
    __tablename__ = "outreach"
    professor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("professors.id", ondelete="CASCADE"))
    email_draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("email_drafts.id", ondelete="SET NULL"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    to_address: Mapped[str | None] = mapped_column(String)
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    # sent | replied | no_response | follow_up_sent | meeting | declined
    status: Mapped[str] = mapped_column(String, default="sent")
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    kind: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String, default="queued")  # queued | running | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
