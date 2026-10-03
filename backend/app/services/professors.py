"""Stage ① Add & Resolve (docs/DESIGN.md §4.1)."""

import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import HomepageCandidate, Professor, School, SourcePage, User
from app.ingest.fetch import FetchResult, fetch
from app.ingest.html import html_to_text, lab_links, own_site_links, recruiting_links, subpage_links
from app.llm import get_llm
from app.llm.schemas import ExtractedProfile, PageText, ParsedEntry
from app.services import evidence as evidence_svc
from app.services.jobs import enqueue, handler
from app.services.schools import get_or_create_school, known_aliases
from app.storage.local import save_bytes, sha256

AUTO_ACCEPT_CONFIDENCE = 0.8
MAX_EXTRA_RECRUITING_PAGES = 3
LINKED_SITE_SUBPAGES = 5  # per linked personal/lab site
MAX_LAB_SITES = 2
# Fields a refresh may overwrite unless the user edited them.
EXTRACTED_FIELDS = ["title", "department", "email", "lab_url", "stated_interests", "bio_summary", "recent_publications"]
# Summarized from evidence (app/services/evidence.py); the user can still override them.
EVIDENCE_FIELDS = ["recruiting_status", "contact_policy"]


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z\s-]", "", name.lower())).strip()


# --- parse + add -------------------------------------------------------------------


SCHOLAR_HOST = re.compile(r"^https?://scholar\.google\.", re.I)
SCHOLAR_MESSAGE = "Google Scholar can't be read automatically. It's saved as a reference — paste their homepage or lab site."


def is_scholar(url: str | None) -> bool:
    return bool(url and SCHOLAR_HOST.match(url.strip()))


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
        if is_scholar(e.url):
            e.issues.append("scholar_link")  # informational: kept as a reference, not used as the homepage
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
        scholar = e.url if is_scholar(e.url) else None
        homepage = None if scholar else e.url
        prof = Professor(
            school_id=school.id, name=e.name, normalized_name=norm, input_raw=e.raw,
            department_raw=e.department_raw, department=e.department_raw, homepage_url=homepage, scholar_url=scholar,
        )
        db.add(prof)
        db.flush()
        if homepage:
            db.add(HomepageCandidate(professor_id=prof.id, url=homepage, source="user", rank=0))
        enqueue(db, "resolve_professor", professor_id=prof.id)
        added.append(prof)
    db.commit()
    return added


def set_homepage(db: Session, prof: Professor, url: str) -> None:
    if is_scholar(url):
        raise ValueError(SCHOLAR_MESSAGE)
    for c in prof.candidates:
        c.chosen = c.url == url
    if not any(c.url == url for c in prof.candidates):
        db.add(HomepageCandidate(professor_id=prof.id, url=url, source="user", rank=0, chosen=True))
    prof.homepage_url, prof.resolve_status, prof.resolve_error = url, "pending", None
    enqueue(db, "resolve_professor", professor_id=prof.id)
    db.commit()


def submit_evidence(
    db: Session, prof: Professor, url: str, quote: str | None, claim: str | None, cycle: str | None,
) -> list:
    """The user points at a page (and optionally the exact sentence) that says something about recruiting.

    With a sentence: it must appear on the page. Without one: the page is read for statements.
    Raises ValueError with a message for the user when nothing usable is found.
    """
    page = next((p for p in prof.source_pages if p.url == url), None) or SourcePage(professor_id=prof.id, url=url)
    db.add(page)
    try:
        r = fetch(url)
    except Exception as e:  # noqa: BLE001 - blocked (403 / bot protection), down, or not found
        return _submit_unreadable(db, prof, page, url, quote, claim, cycle, str(e))
    page.kind = "user_submitted" if page.kind in (None, "user_submitted") else page.kind
    page.final_url = r.final_url
    page.raw_html_path = save_bytes(r.content, "pages", str(prof.id), f"{sha256(r.content)}.html")
    page.text = html_to_text(r.text)
    page.page_updated_at = evidence_svc.page_updated_at(r.last_modified, page.text)
    page.fetch_status, page.error, page.fetched_at = "ok", None, datetime.now(UTC)
    db.flush()
    texts = [PageText(url=page.final_url, text=page.text or "", kind="user_submitted")]

    if quote:
        if not claim:
            raise ValueError("Choose what the sentence says (e.g. Recruiting, Don't email).")
        from app.llm.schemas import Claim

        kind = "recruiting" if claim in ("explicitly_recruiting", "recruits_generally", "not_recruiting") else "contact_policy"
        claims = verified_claims(ExtractedProfile(claims=[
            Claim(kind=kind, claim=claim, cycle=cycle or None, quote=quote.strip(), source_url=page.final_url)
        ]), texts)
        if not claims:
            raise ValueError("That sentence isn't on the page (it must match the page text exactly; copy and paste it).")
        pairs = [(c, evidence_svc.USER) for c in claims]
    else:
        llm = get_llm()
        found = verified_claims(llm.extract_profile(texts, prof.name, prof.school.primary_domain), texts)
        if not found:
            raise ValueError("Couldn't find a recruiting or contact statement on that page. Paste the sentence and choose what it says.")
        pairs = [(c, evidence_svc.USER) for c in found]

    evidence_svc.upsert(db, prof, pairs, [page])
    evidence_svc.apply_summary(prof)
    db.commit()
    return [c for c, _ in pairs]


def _submit_unreadable(
    db: Session, prof: Professor, page: SourcePage, url: str, quote: str | None, claim: str | None, cycle: str | None,
    error: str,
) -> list:
    """The page can't be read automatically. Keep the user's sentence, marked unverified."""
    if not (quote and quote.strip() and claim):
        raise ValueError(
            f"The app can't open that page ({error.splitlines()[0][:120]}). It may block automated visits. "
            "Paste the exact sentence and choose what it says to save it as unverified evidence."
        )
    from app.llm.schemas import Claim

    page.kind = "user_submitted" if page.kind in (None, "user_submitted") else page.kind
    page.fetch_status, page.error, page.fetched_at = "failed", error, datetime.now(UTC)
    kind = "recruiting" if claim in ("explicitly_recruiting", "recruits_generally", "not_recruiting") else "contact_policy"
    c = Claim(kind=kind, claim=claim, cycle=cycle or None, quote=quote.strip(), source_url=url)
    evidence_svc.upsert(db, prof, [(c, evidence_svc.USER)], [page])
    row = next(e for e in prof.evidence if e.source_url == url and e.quote == c.quote and e.kind == kind)
    row.verified = False
    evidence_svc.apply_summary(prof)
    db.commit()
    return [c]


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
        prof.resolve_error = SCHOLAR_MESSAGE if prof.scholar_url else "No homepage found. Paste the professor's homepage URL."
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
    attempted: set[str] = set()

    def load(url: str, kind: str, prefetched: FetchResult | None = None) -> tuple[SourcePage, str | None]:
        attempted.add(url)
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
            page.page_updated_at = evidence_svc.page_updated_at(r.last_modified, page.text)
            page.fetch_status = "ok"
            page.error = "Site's security certificate chain is incomplete; read without verifying it." if r.tls_unverified else None
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
    crawled = {home.url, home.final_url}

    def explore(root: SourcePage, root_html: str, max_subpages: int, kind: str = "subpage") -> None:
        """Subpages of one site (within its scope), then one more hop for "Open positions" links."""
        root_url = root.final_url or root.url
        sub_html: list[tuple[SourcePage, str]] = []
        for url in subpage_links(root_html, root_url, max_subpages):
            if url in crawled:
                continue
            page, html = load(url, kind)
            crawled.update({url, page.final_url})
            if page.fetch_status == "ok":
                pages.append(page)
                sub_html.append((page, html or ""))
        extra: list[str] = []
        for page, html in [(root, root_html), *sub_html]:
            for url in recruiting_links(html, page.final_url or page.url, root_url):
                if url not in crawled and url not in extra:
                    extra.append(url)
        for url in extra[:MAX_EXTRA_RECRUITING_PAGES]:
            page, _ = load(url, kind)
            crawled.update({url, page.final_url})
            if page.fetch_status == "ok":
                pages.append(page)

    explore(home, home_html or "", settings.max_subpages)
    # A directory profile often links to the professor's own site ("Research Website", "Lab").
    # Explore that site like a homepage: that's where Join / Open positions pages usually live.
    linked = [u for u in own_site_links(home_html or "", home.final_url or home.url) if u not in crawled]
    labs: list[str] = []
    for url in linked:
        page, html = load(url, "linked_site")
        crawled.update({url, page.final_url})
        if page.fetch_status == "ok":
            pages.append(page)
            explore(page, html or "", LINKED_SITE_SUBPAGES)
            labs += [u for u in lab_links(html or "", page.final_url or url) if u not in labs]
    # One more site: the lab linked from their personal site (join / contact notes often live there).
    for url in [u for u in labs if u not in crawled][:MAX_LAB_SITES]:
        page, html = load(url, "lab_site")
        crawled.update({url, page.final_url})
        if page.fetch_status == "ok":
            pages.append(page)
            explore(page, html or "", LINKED_SITE_SUBPAGES, kind="lab_site")
    # Pages the user submitted as evidence are always re-read.
    for submitted in [p for p in existing.values() if p.kind == "user_submitted"]:
        page, _ = load(submitted.url, "user_submitted")
        if page.fetch_status == "ok":
            pages.append(page)
    failed_urls = {p.url for p in existing.values() if p.fetch_status == "failed"}
    failed_urls |= {p.url for p in db.new if isinstance(p, SourcePage) and p.fetch_status == "failed"}
    # Drop pages from earlier crawls that this crawl no longer links to. Pages that failed to load
    # this time stay (and are listed as unreadable); pages the user submitted always stay.
    for url, stale in existing.items():
        if url not in attempted and stale.kind != "user_submitted":
            db.delete(stale)
    db.flush()

    page_texts = [PageText(url=p.final_url or p.url, text=p.text or "", kind=p.kind) for p in pages]
    llm = get_llm()
    extracted = llm.extract_profile(page_texts, prof.name, prof.school.primary_domain)
    extracted.claims = verified_claims(extracted, page_texts)
    if linked and not extracted.lab_url:
        extracted.lab_url = linked[0]
    _apply_extracted(prof, extracted)
    user = verified_claims(ExtractedProfile(claims=evidence_svc.user_claims(prof)), page_texts)
    evidence_svc.record(
        db, prof, [(c, llm.name) for c in extracted.claims] + [(c, evidence_svc.USER) for c in user], pages, failed_urls,
    )
    evidence_svc.apply_summary(prof)

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


MIN_QUOTE_CHARS = 15


def verified_claims(extracted: ExtractedProfile, pages: list[PageText]) -> list:
    """Keep only claims whose quote really appears on the page it cites.

    Quotes must be a real sentence fragment: an empty or tiny quote "appears" on every page.
    """
    texts = {p.url: _squash(p.text) for p in pages}
    return [
        c for c in extracted.claims
        if len(_squash(c.quote)) >= MIN_QUOTE_CHARS and _squash(c.quote) in texts.get(c.source_url, "")
    ]


def _apply_extracted(prof: Professor, x: ExtractedProfile) -> None:
    values = {
        "title": x.title,
        "department": ", ".join(x.departments) if x.departments else prof.department,
        "email": x.email,
        "lab_url": x.lab_url,
        "stated_interests": x.stated_interests,
        "bio_summary": x.bio_summary,
        "recent_publications": [p.model_dump() for p in x.recent_publications],
    }
    for field in EXTRACTED_FIELDS:
        if field not in prof.user_overrides:
            setattr(prof, field, values[field])
    prof.field_sources = x.field_sources
