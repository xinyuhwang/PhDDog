import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.llm.schemas import ParsedEntry, StructuredProfile


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProfileOut(ORM):
    version: int
    resume_file_path: str | None
    resume_text: str | None
    research_statement: str | None
    keywords: list[str]
    structured_profile: StructuredProfile | None
    created_at: datetime


class ProfileIn(BaseModel):
    research_statement: str | None = None
    keywords: list[str] = []


class ParseIn(BaseModel):
    text: str


class BulkIn(BaseModel):
    entries: list[ParsedEntry]


class SchoolOut(ORM):
    id: uuid.UUID
    name: str
    aliases: list[str]
    primary_domain: str | None
    confirmed: bool
    suggestions: list[dict]
    is_target: bool
    professor_count: int = 0


class SchoolCreateIn(BaseModel):
    name: str
    is_target: bool = True


class SchoolTargetIn(BaseModel):
    is_target: bool


class SchoolConfirmIn(BaseModel):
    name: str
    primary_domain: str | None = None
    aliases: list[str] = []


class CandidateOut(ORM):
    id: uuid.UUID
    url: str
    source: str
    confidence: float | None
    reason: str | None
    chosen: bool


class ScreenOut(ORM):
    score: float
    label: str
    reason: str
    profile_version: int


class ProfessorSummary(ORM):
    id: uuid.UUID
    name: str
    school_name: str
    department: str | None
    title: str | None
    email: str | None
    homepage_url: str | None
    resolve_status: str
    resolve_error: str | None
    recruiting_status: str
    recruiting_cycle: str | None
    recruiting_stale: bool
    recruiting_confidence: str | None
    contact_policy: str
    last_checked_at: datetime | None
    check_stale: bool = False  # last site check is older than RECHECK_AFTER_DAYS
    notes: str | None = None
    status: str
    screen: ScreenOut | None = None


class EvidenceOut(ORM):
    id: uuid.UUID
    kind: str
    claim: str
    cycle: str | None
    quote: str
    source_url: str
    source_type: str
    page_updated_at: datetime | None
    first_seen_at: datetime
    last_seen_at: datetime
    gone_at: datetime | None
    extractor: str
    verified: bool


class ProfessorDetail(ProfessorSummary):
    input_raw: str | None
    lab_url: str | None
    scholar_url: str | None
    resolve_confidence: float | None
    stated_interests: str | None
    bio_summary: str | None
    recent_publications: list[dict]
    recruiting_evidence: str | None
    recruiting_source_url: str | None
    contact_evidence: str | None
    contact_source_url: str | None
    field_sources: dict
    user_overrides: list[str]
    evidence: list[EvidenceOut]
    candidates: list[CandidateOut]
    pages: list[dict]


class ProfessorPatch(BaseModel):
    name: str | None = None
    title: str | None = None
    department: str | None = None
    email: str | None = None
    lab_url: str | None = None
    scholar_url: str | None = None
    stated_interests: str | None = None
    recruiting_status: str | None = None
    contact_policy: str | None = None
    status: str | None = None
    notes: str | None = None


class HomepageIn(BaseModel):
    url: str


class EvidenceIn(BaseModel):
    url: str
    quote: str | None = None
    claim: Literal[
        "explicitly_recruiting", "recruits_generally", "not_recruiting",
        "welcomes_email", "apply_via_program", "do_not_email",
    ] | None = None
    cycle: str | None = None


class PaperUrlIn(BaseModel):
    url: str


class PaperOut(ORM):
    id: uuid.UUID
    source_type: str
    source_url: str | None
    title: str | None
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    abstract: str | None
    text_status: str
    error: str | None
    summary: dict | None
    text_chars: int = 0
    year_warning: bool = False
    created_at: datetime


class ConnectionPointOut(ORM):
    id: uuid.UUID
    paper_id: uuid.UUID
    paper_title: str | None = None
    kind: str
    paper_evidence: str
    user_evidence: str
    explanation: str
    selected: bool


class ConnectionSelectIn(BaseModel):
    selected: bool


class DraftIn(BaseModel):
    connection_point_ids: list[uuid.UUID] = []
    tone: Literal["formal", "warm"] = "formal"
    ask: Literal["phd", "ra", "both"] = "both"


class DraftEditIn(BaseModel):
    subject: str
    body: str


class DraftOut(ORM):
    id: uuid.UUID
    version: int
    subject: str
    body: str
    tone: str
    ask: str
    connection_point_ids: list[str]
    model: str | None
    edited_by_user: bool
    created_at: datetime


class SendIn(BaseModel):
    draft_id: uuid.UUID
    to_address: str | None = None
    sent_at: datetime | None = None


OutreachStatus = Literal["sent", "replied", "no_response", "follow_up_sent", "meeting", "declined"]


class OutreachOut(ORM):
    id: uuid.UUID
    professor_id: uuid.UUID
    professor_name: str | None = None
    school_name: str | None = None
    sent_at: datetime
    to_address: str | None
    subject: str
    body: str
    status: str
    follow_up_at: datetime | None
    notes: str | None


class OutreachPatch(BaseModel):
    status: OutreachStatus | None = None
    follow_up_at: datetime | None = None
    notes: str | None = None


class JobOut(ORM):
    id: uuid.UUID
    kind: str
    status: str
    attempts: int
    error: str | None
    payload: dict
    created_at: datetime
    finished_at: datetime | None
