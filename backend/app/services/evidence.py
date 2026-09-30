"""Recruiting / contact-policy evidence (docs/DESIGN.md §4.1).

Extraction (a model or the offline rules) only finds and quotes statements. Everything else is
deterministic code here: where a statement came from, when it was seen, whether it has since
disappeared, and the professor's overall status and confidence.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Evidence, Professor, SourcePage
from app.llm.schemas import Claim

# How much a source speaks for the professor personally.
TRUST = {"personal": 3, "lab": 3, "faculty_profile": 2, "admissions": 1, "department": 1, "other": 1}
CONTACT_STRICTNESS = {"do_not_email": 3, "apply_via_program": 2, "welcomes_email": 1}

PERSONAL_HOSTS = re.compile(r"(\.github\.io|sites\.google\.com|\.netlify\.app|\.vercel\.app|\.wixsite\.com)$", re.I)
DIRECTORY_PATH = re.compile(r"/(people|person|faculty|profiles?|directory|staff|bio)/", re.I)
LAB_HOST = re.compile(r"(lab|labs|group)(\.|$)", re.I)
LAB_PATH = re.compile(r"/(lab|labs|group|research-group)(/|$)", re.I)
ADMISSIONS_PATH = re.compile(r"(admission|/apply|prospective-students|graduate-program|phd-program)", re.I)
# First host label of department / directory sites (vs. a person-named subdomain like sharathg.cis.upenn.edu).
GENERIC_LABELS = {
    "www", "cs", "cse", "ece", "eecs", "cis", "seas", "engineering", "profiles", "people", "faculty", "directory",
    "med", "medicine", "experts", "scholars", "research",
}


def cycle_year(cycle: str | None) -> int | None:
    m = re.search(r"(20\d{2})", cycle or "")
    return int(m.group(1)) if m else None


def classify_source(url: str, page_kind: str, school_domain: str | None) -> str:
    """personal | lab | faculty_profile | admissions, from the URL. (department / other are reserved.)"""
    parts = urlsplit(url)
    host, path = parts.netloc.lower().split(":")[0].removeprefix("www."), parts.path
    if ADMISSIONS_PATH.search(path):
        return "admissions"
    if page_kind == "lab_site":  # reached through a "… Lab" link from their own site
        return "lab"
    if LAB_HOST.search(host.split(".")[0]) or LAB_PATH.search(path):
        return "lab"
    if PERSONAL_HOSTS.search(host) or "/~" in path:
        return "personal"
    on_school_site = bool(school_domain and (host == school_domain or host.endswith("." + school_domain)))
    if not on_school_site:
        return "personal"  # their own domain, linked from the profile or given by the user
    if DIRECTORY_PATH.search(path) or host.split(".")[0] in GENERIC_LABELS:
        return "faculty_profile"
    return "personal"


UPDATED_TEXT = re.compile(
    r"\b(?:last\s+)?(?:updated|modified)\s*(?:on|:)?\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2},?\s+)?\d{4}|\d{4}-\d{2}-\d{2})",
    re.I,
)


def page_updated_at(last_modified_header: str | None, text: str | None) -> datetime | None:
    """The page's own "last updated" date: on-page text first (authored), then the HTTP header."""
    if text and (m := UPDATED_TEXT.search(text)):
        raw = re.sub(r"[.,]", "", m.group(1)).replace("Sept", "Sep")
        for fmt in ("%Y-%m-%d", "%B %d %Y", "%b %d %Y", "%B %Y", "%b %Y"):
            try:
                return datetime.strptime(raw.title() if fmt != "%Y-%m-%d" else raw, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
    if last_modified_header:
        try:
            return parsedate_to_datetime(last_modified_header)
        except (TypeError, ValueError):
            return None
    return None


def _hash(quote: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", quote).strip().lower().encode()).hexdigest()[:32]


USER = "user"  # extractor name for evidence the user submitted


def upsert(db: Session, prof: Professor, claims: list[tuple[Claim, str]], pages: list[SourcePage]) -> set[tuple]:
    """Add or refresh evidence rows for (claim, extractor) pairs. Returns the keys seen."""
    now = datetime.now(UTC)
    school_domain = prof.school.primary_domain
    page_by_url = {p.final_url or p.url: p for p in pages}
    existing = {(e.kind, e.source_url, e.quote_hash): e for e in prof.evidence}
    seen: set[tuple] = set()
    for c, extractor in claims:
        key = (c.kind, c.source_url, _hash(c.quote))
        seen.add(key)
        page = page_by_url.get(c.source_url)
        if (row := existing.get(key)) is None:
            row = Evidence(
                professor_id=prof.id, kind=c.kind, quote=c.quote, quote_hash=key[2], source_url=c.source_url,
                first_seen_at=now, extractor=extractor,
            )
            db.add(row)
            prof.evidence.append(row)
            existing[key] = row
        elif row.extractor == USER:
            extractor = USER  # a statement the user vouched for stays theirs
        row.claim, row.cycle = c.claim, c.cycle
        row.source_type = classify_source(c.source_url, page.kind if page else "other", school_domain)
        row.page_updated_at = page.page_updated_at if page else None
        row.last_seen_at, row.gone_at, row.extractor, row.verified = now, None, extractor, True
    return seen


def record(
    db: Session, prof: Professor, claims: list[tuple[Claim, str]], pages: list[SourcePage], failed_urls: set[str],
) -> None:
    """Upsert a full crawl's claims. Earlier claims no longer found on a page we re-read are marked gone."""
    now = datetime.now(UTC)
    seen = upsert(db, prof, claims, pages)
    read_ok = {p.final_url or p.url for p in pages}
    for row in prof.evidence:
        key = (row.kind, row.source_url, row.quote_hash)
        if key in seen or row.gone_at is not None:
            continue
        # Gone only if we re-read the page and the sentence is missing, or the page is no longer linked
        # in a crawl where nothing failed. A failed page (or one we couldn't reach because the page
        # linking to it failed) says nothing either way.
        if row.source_url in read_ok or (not failed_urls and row.source_url not in read_ok):
            row.gone_at = now


def user_claims(prof: Professor) -> list[Claim]:
    """Statements the user submitted, to re-check on every crawl like any other evidence."""
    return [
        Claim(kind=e.kind, claim=e.claim, cycle=e.cycle, quote=e.quote, source_url=e.source_url)
        for e in prof.evidence if e.extractor == USER
    ]


@dataclass
class Summary:
    recruiting_status: str
    recruiting_cycle: str | None
    recruiting_stale: bool
    recruiting_confidence: str | None
    recruiting: Evidence | None
    contact_policy: str
    contact: Evidence | None


def summarize(evidence: list[Evidence], target_cycle: str) -> Summary:
    """Pick the statement that best answers "are they recruiting for my cycle?", and rate how sure we are.

    Preference: a statement naming the target cycle (or later) > an undated statement > one naming an
    earlier cycle; then the more personal source; then explicit statements over "every year" ones.
    """
    target = cycle_year(target_cycle)
    current = [e for e in evidence if e.gone_at is None]

    def freshness(e: Evidence) -> int:
        year = cycle_year(e.cycle)
        if year is None:
            return 1
        return 2 if target is None or year >= target else 0

    recruiting = [e for e in current if e.kind == "recruiting"]
    # An undated general statement ("apply and name me") on a page that also has a dated one belongs to
    # that dated statement; it mustn't make an old cycle look current.
    dated_pages = {e.source_url for e in recruiting if e.cycle}
    recruiting = [e for e in recruiting if e.cycle or e.claim != "recruits_generally" or e.source_url not in dated_pages]
    best = max(
        recruiting,
        key=lambda e: (freshness(e), TRUST.get(e.source_type, 1), e.claim != "recruits_generally", e.last_seen_at),
        default=None,
    )
    if best is None:
        status, cycle, stale, confidence = "unknown", None, False, None
    else:
        status, cycle = best.claim, best.cycle
        stale = freshness(best) == 0
        trusted = TRUST.get(best.source_type, 1) >= 2
        if stale or not trusted:
            confidence = "low"
        elif freshness(best) == 2 and best.claim != "recruits_generally" and best.verified is not False:
            confidence = "high"
        else:
            confidence = "medium"  # includes sentences the app couldn't check on the page itself

    contacts = [e for e in current if e.kind == "contact_policy"]
    own = [e for e in contacts if TRUST.get(e.source_type, 1) >= 2] or contacts
    contact = max(own, key=lambda e: (CONTACT_STRICTNESS.get(e.claim, 0), e.last_seen_at), default=None)

    return Summary(
        recruiting_status=status, recruiting_cycle=cycle, recruiting_stale=stale, recruiting_confidence=confidence,
        recruiting=best, contact_policy=contact.claim if contact else "unknown", contact=contact,
    )


def apply_summary(prof: Professor) -> None:
    """Cache the summary on the professor row (used for lists and sorting). User edits win."""
    s = summarize(prof.evidence, get_settings().target_cycle)
    values = {
        "recruiting_status": s.recruiting_status,
        "recruiting_cycle": s.recruiting_cycle,
        "recruiting_evidence": s.recruiting.quote if s.recruiting else None,
        "recruiting_source_url": s.recruiting.source_url if s.recruiting else None,
        "contact_policy": s.contact_policy,
        "contact_evidence": s.contact.quote if s.contact else None,
        "contact_source_url": s.contact.source_url if s.contact else None,
    }
    for field, value in values.items():
        if field not in prof.user_overrides:
            setattr(prof, field, value)
    prof.recruiting_stale = s.recruiting_stale
    prof.recruiting_confidence = s.recruiting_confidence if "recruiting_status" not in prof.user_overrides else None
