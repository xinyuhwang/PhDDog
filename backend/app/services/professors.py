"""Stage ① Add & Resolve (docs/DESIGN.md §4.1)."""

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import HomepageCandidate, Professor, School, SourcePage, User
from app.ingest.fetch import FetchResult, fetch
from app.ingest.html import html_to_text, own_site_links, subpage_links
from app.llm import get_llm
from app.llm.schemas import ExtractedProfile, PageText, ParsedEntry
from app.services.jobs import enqueue, handler
from app.services.schools import get_or_create_school, known_aliases
from app.storage.local import save_bytes, sha256

AUTO_ACCEPT_CONFIDENCE = 0.8
# Fields a refresh may overwrite unless the user edited them.
EXTRACTED_FIELDS = [
    "title", "department", "email", "lab_url", "stated_interests", "bio_summary", "recent_publications",
    "recruiting_status", "recruiting_cycle", "recruiting_evidence", "recruiting_source_url",
    "contact_policy", "contact_evidence", "contact_source_url",
]


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z\s-]", "", name.lower())).strip()


# --- parse + add -------------------------------------------------------------------


def parse_input(db: Session, user: User, text: str) -> list[ParsedEntry]:
    aliases = known_aliases(db, user)
    entries = get_llm().parse_professor_input(text, aliases)
    for e in entries:
        if e.name and e.school_raw:
            canonical = aliases.get(e.school_raw.lower(), e.school_raw)
            exists = db.scalar(
                select(Professor.id).join(School).where(
                    School.user_id == user.id, School.name == canonical,
                    Professor.normalized_name == normalize_name(e.name),
                )
            )
            if exists:
                e.issues.append("duplicate")
    return entries


def add_professors(db: Session, user: User, entries: list[ParsedEntry]) -> list[Professor]:
    added = []
    for e in entries:
        if not e.name or not e.school_raw or "duplicate" in e.issues:
            continue
        school = get_or_create_school(db, user, e.school_raw)
        norm = normalize_name(e.name)
        if db.scalar(select(Professor).where(Professor.school_id == school.id, Professor.normalized_name == norm)):
            continue
        prof = Professor(
            school_id=school.id, name=e.name, normalized_name=norm, input_raw=e.raw,
            department_raw=e.department_raw, department=e.department_raw, homepage_url=e.url,
        )
        db.add(prof)
        db.flush()
        if e.url:
            db.add(HomepageCandidate(professor_id=prof.id, url=e.url, source="user", rank=0))
        enqueue(db, "resolve_professor", professor_id=prof.id)
        added.append(prof)
    db.commit()
    return added


def set_homepage(db: Session, prof: Professor, url: str) -> None:
    for c in prof.candidates:
        c.chosen = c.url == url
    if not any(c.url == url for c in prof.candidates):
        db.add(HomepageCandidate(professor_id=prof.id, url=url, source="user", rank=0, chosen=True))
    prof.homepage_url, prof.resolve_status, prof.resolve_error = url, "pending", None
    enqueue(db, "resolve_professor", professor_id=prof.id)
    db.commit()


def request_refresh(db: Session, prof: Professor) -> None:
    enqueue(db, "extract_profile", professor_id=prof.id, force=True)
    db.commit()


# --- resolve job ---------------------------------------------------------------------


@handler("resolve_professor")
def resolve_professor(db: Session, payload: dict) -> None:
    prof = db.get(Professor, uuid.UUID(payload["professor_id"]))
    school = prof.school
    llm = get_llm()

    user_url = prof.homepage_url
    if not user_url and not prof.candidates:
        for rank, c in enumerate(llm.find_homepage(prof.name, school.name, school.primary_domain, prof.department_raw)[:3]):
            db.add(HomepageCandidate(professor_id=prof.id, url=c.url, source="search", rank=rank + 1, reason=c.reason))
        db.flush()
        db.refresh(prof)

    if not prof.candidates:
        prof.resolve_status = "not_found"
        prof.resolve_error = "No homepage found. Paste the professor's homepage URL."
        return

    best: tuple[float, HomepageCandidate, FetchResult] | None = None
    for cand in prof.candidates[:3]:
        if user_url and cand.url != user_url:
            continue
        try:
            page = fetch(cand.url)
        except Exception as e:  # noqa: BLE001
            cand.confidence, cand.reason = 0.0, f"Fetch failed: {e}"
            continue
        v = llm.verify_homepage(
            PageText(url=page.final_url, text=html_to_text(page.text)), prof.name, school.name, school.aliases,
            school.primary_domain,
        )
        cand.confidence, cand.reason = v.confidence, v.reason
        if best is None or v.confidence > best[0]:
            best = (v.confidence, cand, page)

    if best is None:
        prof.resolve_status = "needs_review" if not user_url else "not_found"
        prof.resolve_error = "Could not fetch any candidate page."
        return

    confidence, cand, page = best
    # A URL the user typed or picked is trusted; search results must clear the confidence bar.
    if cand.source == "user" or cand.chosen or confidence >= AUTO_ACCEPT_CONFIDENCE:
        cand.chosen = True
        prof.homepage_url = page.final_url
        prof.resolve_confidence = confidence
        crawl_and_extract(db, prof, homepage=page)
    else:
        prof.resolve_status = "needs_review"
        prof.resolve_confidence = confidence
        prof.resolve_error = "Not sure this is the right person. Pick a candidate or paste the URL."


@handler("extract_profile")
def extract_profile_job(db: Session, payload: dict) -> None:
    prof = db.get(Professor, uuid.UUID(payload["professor_id"]))
    if not prof.homepage_url:
        raise ValueError("Professor has no homepage URL yet")
    crawl_and_extract(db, prof, force=bool(payload.get("force")))


def crawl_and_extract(db: Session, prof: Professor, homepage: FetchResult | None = None, force: bool = False) -> None:
    settings = get_settings()
    fresh_after = datetime.now(UTC) - timedelta(days=settings.fetch_cache_days)
    existing = {p.url: p for p in prof.source_pages}

    def load(url: str, kind: str, prefetched: FetchResult | None = None) -> tuple[SourcePage, str | None]:
        page = existing.get(url)
        if page and not force and page.fetch_status == "ok" and page.fetched_at and page.fetched_at > fresh_after and not prefetched:
            html = open(page.raw_html_path).read() if page.raw_html_path else None
            return page, html
        page = page or SourcePage(professor_id=prof.id, url=url, kind=kind)
        db.add(page)
        try:
            r = prefetched or fetch(url)
            html = r.text
            page.final_url = r.final_url
            page.raw_html_path = save_bytes(r.content, "pages", str(prof.id), f"{sha256(r.content)}.html")
            page.text = html_to_text(html)
            page.fetch_status, page.error = "ok", None
        except Exception as e:  # noqa: BLE001
            html = None
            page.fetch_status, page.error = "failed", str(e)
        page.fetched_at = datetime.now(UTC)
        return page, html

    home, home_html = load(prof.homepage_url, "homepage", homepage)
    if home.fetch_status != "ok":
        prof.resolve_status, prof.resolve_error = "not_found", f"Homepage fetch failed: {home.error}"
        return
    pages = [home]
    base = home.final_url or home.url
    for url in subpage_links(home_html or "", base, settings.max_subpages):
        page, _ = load(url, "subpage")
        if page.fetch_status == "ok":
            pages.append(page)
    # A directory profile often links to the professor's own site ("Website", "Lab"); read its front page too.
    linked = own_site_links(home_html or "", base)
    for url in linked:
        page, _ = load(url, "linked_site")
        if page.fetch_status == "ok":
            pages.append(page)
    # Drop pages from earlier crawls that this crawl no longer reaches.
    for stale in set(existing.values()) - set(pages):
        db.delete(stale)
    db.flush()

    page_texts = [PageText(url=p.final_url or p.url, text=p.text or "", kind=p.kind) for p in pages]
    extracted = get_llm().extract_profile(page_texts, prof.name, prof.school.primary_domain)
    _drop_unverified_quotes(extracted, page_texts)
    if linked and not extracted.lab_url:
        extracted.lab_url = linked[0]
    _apply_extracted(prof, extracted)

    prof.resolve_status, prof.resolve_error = "resolved", None
    prof.last_checked_at = datetime.now(UTC)
    if prof.status == "added":
        prof.status = "resolved"

    from app.services.profile import active_profile
    from app.services.screen import screen_one

    user = db.get(User, prof.school.user_id)
    if profile := active_profile(db, user):
        screen_one(db, profile, prof)


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _drop_unverified_quotes(extracted: ExtractedProfile, pages: list[PageText]) -> None:
    """A recruiting/contact claim must quote text that is really on the page it cites."""
    texts = {p.url: _squash(p.text) for p in pages}
    for field in ("recruiting_evidence", "contact_evidence"):
        ev = getattr(extracted, field)
        if ev and _squash(ev.quote) not in texts.get(ev.source_url, ""):
            setattr(extracted, field, None)
            if field == "recruiting_evidence":
                extracted.recruiting_status, extracted.recruiting_cycle = "unknown", None
            else:
                extracted.contact_policy = "unknown"


def cycle_year(cycle: str | None) -> int | None:
    m = re.search(r"(20\d{2})", cycle or "")
    return int(m.group(1)) if m else None


def _apply_extracted(prof: Professor, x: ExtractedProfile) -> None:
    values = {
        "title": x.title,
        "department": ", ".join(x.departments) if x.departments else prof.department,
        "email": x.email,
        "lab_url": x.lab_url,
        "stated_interests": x.stated_interests,
        "bio_summary": x.bio_summary,
        "recent_publications": [p.model_dump() for p in x.recent_publications],
        "recruiting_status": x.recruiting_status,
        "recruiting_cycle": x.recruiting_cycle,
        "recruiting_evidence": x.recruiting_evidence.quote if x.recruiting_evidence else None,
        "recruiting_source_url": x.recruiting_evidence.source_url if x.recruiting_evidence else None,
        "contact_policy": x.contact_policy,
        "contact_evidence": x.contact_evidence.quote if x.contact_evidence else None,
        "contact_source_url": x.contact_evidence.source_url if x.contact_evidence else None,
    }
    for field in EXTRACTED_FIELDS:
        if field not in prof.user_overrides:
            setattr(prof, field, values[field])
    prof.field_sources = x.field_sources
    target = cycle_year(get_settings().target_cycle)
    year = cycle_year(prof.recruiting_cycle)
    prof.recruiting_stale = bool(target and year and year < target)
