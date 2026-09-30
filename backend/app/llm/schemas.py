"""Structured inputs/outputs for every LLM task (docs/DESIGN.md §7).

The same models are used by the fake provider and, later, as the
`messages.parse()` output schemas for the Claude provider.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

RecruitingStatus = Literal["explicitly_recruiting", "recruits_generally", "not_recruiting", "unknown"]
ContactPolicy = Literal["welcomes_email", "apply_via_program", "do_not_email", "unknown"]
ClaimKind = Literal["recruiting", "contact_policy"]
ClaimValue = Literal[
    "explicitly_recruiting", "recruits_generally", "not_recruiting",  # kind = recruiting
    "welcomes_email", "apply_via_program", "do_not_email",  # kind = contact_policy
]
ScreenLabel = Literal["strong", "possible", "no"]
ConnectionKind = Literal["method_overlap", "domain_overlap", "future_work_hook"]


@dataclass
class PageText:
    url: str
    text: str
    kind: str = "homepage"  # homepage | subpage | directory


class ParsedEntry(BaseModel):
    raw: str
    name: str | None = None
    school_raw: str | None = None
    department_raw: str | None = None
    url: str | None = None
    issues: list[str] = Field(default_factory=list)  # missing_school | unclear_name | duplicate


class SchoolInfo(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    primary_domain: str | None = None
    known: bool = False  # True if recognized with confidence; False means "please confirm"


class CandidateOut(BaseModel):
    url: str
    reason: str


class HomepageVerification(BaseModel):
    is_match: bool
    confidence: float
    reason: str


class Claim(BaseModel):
    """One statement on a page about recruiting or how to contact the professor, quoted verbatim."""

    kind: ClaimKind
    claim: ClaimValue
    cycle: str | None = None  # e.g. "Fall 2026" if the statement names one
    quote: str
    source_url: str


class PubRef(BaseModel):
    title: str
    year: int | None = None
    url: str | None = None


class ExtractedProfile(BaseModel):
    title: str | None = None
    departments: list[str] = Field(default_factory=list)
    email: str | None = None
    lab_url: str | None = None
    stated_interests: str | None = None
    bio_summary: str | None = None
    recent_publications: list[PubRef] = Field(default_factory=list)
    # Every recruiting / contact statement found. Status and confidence are computed from these in code.
    claims: list[Claim] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)


class ResumeItem(BaseModel):
    title: str
    description: str


class StructuredProfile(BaseModel):
    interests: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    experiences: list[ResumeItem] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)


class ScreenOutput(BaseModel):
    label: ScreenLabel
    score: float
    reason: str


class PaperSummary(BaseModel):
    problem: str = ""
    methods: list[str] = Field(default_factory=list)
    data_modalities: list[str] = Field(default_factory=list)
    application_setting: str = ""
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    future_work: list[str] = Field(default_factory=list)


class ConnectionOut(BaseModel):
    kind: ConnectionKind
    paper_evidence: str
    user_evidence: str
    explanation: str


class EmailOut(BaseModel):
    subject: str
    body: str
