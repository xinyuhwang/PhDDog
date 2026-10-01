"""End-to-end through the API in fake mode: resume -> add -> resolve -> screen -> paper -> connections -> email -> log."""

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.ingest.fetch import FetchResult

HOME_HTML = """<html><body>
<h1>Jacob Gardner</h1>
<p>Jacob Gardner is an Assistant Professor in the Department of Computer and Information Science at the University of Pennsylvania.</p>
<p>My research focuses on machine learning for medical imaging and drug discovery.</p>
<a href="/join.html">Prospective students</a>
<a href="https://elsewhere.example.com/join">Offsite link</a>
</body></html>"""
JOIN_HTML = """<html><body><p>I am looking for PhD students for the Fall 2025 application / Fall 2026 start cycle.
If you are interested, apply to the CIS PhD Program directly, but do mention me in your application!</p></body></html>"""


def fake_fetch(url: str, check_robots: bool = True) -> FetchResult:
    pages = {"https://jg.example.edu/": HOME_HTML, "https://jg.example.edu/join.html": JOIN_HTML}
    if url not in pages:
        raise RuntimeError(f"unexpected fetch {url}")
    return FetchResult(url=url, final_url=url, status_code=200, content_type="text/html", content=pages[url].encode())


def make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


RESUME = (
    "Jane Student\nResearch Experience\n"
    "Built a deep learning model for medical imaging segmentation of MRI scans at a hospital lab.\n"
    "Applied machine learning to drug discovery using molecular graphs.\n"
    "Skills: Python, PyTorch, SQL"
)
PAPER = (
    "Scalable Bayesian Optimization for Drug Discovery\n\nAbstract\n"
    "We study machine learning methods for drug discovery and propose a new approach that improves sample "
    "efficiency when searching large molecular spaces with expensive evaluations and noisy measurements.\n\n"
    "1 Introduction\n" + ("Deep learning and medical imaging remain important. " * 80)
    + "\nIn future work, we plan to extend this approach to medical imaging with deep learning."
)


@pytest.fixture()
def client(database, monkeypatch):
    import app.services.professors as prof_svc
    from app.main import app

    monkeypatch.setattr(prof_svc, "fetch", fake_fetch)
    monkeypatch.setattr(prof_svc.get_llm(), "_homepages", {})
    return TestClient(app)


def run_jobs():
    from app.db.session import SessionLocal
    from app.services.jobs import run_pending

    with SessionLocal() as db:
        run_pending(db)


def test_full_flow(client):
    assert client.post("/professors/screen").status_code == 400  # no profile yet

    r = client.post("/profile/resume", files={"file": ("cv.pdf", make_pdf(RESUME), "application/pdf")})
    assert r.status_code == 200, r.text
    assert "medical imaging" in r.json()["structured_profile"]["domains"]

    preview = client.post("/professors/parse", json={"text": "Jacob Gardner (UPenn CIS) https://jg.example.edu/\nNo School Person"}).json()
    assert preview[0]["school_raw"] == "UPenn" and preview[0]["url"] == "https://jg.example.edu/"
    assert "missing_school" in preview[1]["issues"]

    added = client.post("/professors/bulk", json={"entries": preview}).json()
    assert len(added) == 1  # the entry with no school is skipped
    pid = added[0]["id"]
    run_jobs()

    prof = client.get(f"/professors/{pid}").json()
    assert prof["resolve_status"] == "resolved", prof["resolve_error"]
    assert prof["school_name"] == "University of Pennsylvania"
    assert prof["title"] == "Assistant Professor"
    assert prof["recruiting_status"] == "explicitly_recruiting"
    assert prof["recruiting_cycle"] == "Fall 2026" and prof["recruiting_stale"] is True
    assert prof["contact_policy"] == "apply_via_program"
    assert prof["recruiting_source_url"] == "https://jg.example.edu/join.html"
    assert [p["url"] for p in prof["pages"]] == ["https://jg.example.edu/", "https://jg.example.edu/join.html"]
    assert prof["screen"]["label"] == "strong"  # auto-screened after extraction

    # Adding the same professor again is flagged as a duplicate.
    again = client.post("/professors/parse", json={"text": "Jacob Gardner, Penn"}).json()
    assert "duplicate" in again[0]["issues"]

    # User edits survive a refresh.
    client.patch(f"/professors/{pid}", json={"title": "Professor (edited)"})
    client.post(f"/professors/{pid}/refresh")
    run_jobs()
    assert client.get(f"/professors/{pid}").json()["title"] == "Professor (edited)"

    paper = client.post(f"/professors/{pid}/papers/pdf", files={"file": ("p.pdf", make_pdf(PAPER), "application/pdf")}).json()
    assert paper["text_status"] == "full"
    run_jobs()
    [paper] = client.get(f"/professors/{pid}/papers").json()
    assert "drug discovery" in paper["summary"]["application_setting"]

    client.post(f"/professors/{pid}/analyze")
    run_jobs()
    conns = client.get(f"/professors/{pid}/connections").json()
    kinds = {c["kind"] for c in conns}
    assert {"method_overlap", "future_work_hook"} <= kinds

    draft = client.post(f"/professors/{pid}/drafts", json={"connection_point_ids": [conns[0]["id"]], "tone": "formal", "ask": "phd"}).json()
    assert draft["version"] == 1 and "Dear Professor Gardner" in draft["body"]
    edited = client.put(f"/drafts/{draft['id']}", json={"subject": "Hello", "body": "Edited body"}).json()
    assert edited["version"] == 2 and edited["edited_by_user"]

    sent = client.post(f"/professors/{pid}/outreach", json={"draft_id": edited["id"]}).json()
    assert sent["body"] == "Edited body" and sent["status"] == "sent" and sent["follow_up_at"]
    client.patch(f"/outreach/{sent['id']}", json={"status": "replied", "notes": "Wants a call"})
    [record] = client.get("/outreach").json()
    assert record["status"] == "replied" and record["professor_name"] == "Jacob Gardner"
    assert client.get(f"/professors/{pid}").json()["status"] == "replied"


def test_needs_review_when_no_homepage_found(client):
    added = client.post("/professors/bulk", json={"entries": [{"raw": "x", "name": "Ada Lovelace", "school_raw": "MIT"}]}).json()
    run_jobs()
    prof = client.get(f"/professors/{added[0]['id']}").json()
    assert prof["resolve_status"] == "not_found"

    client.post(f"/professors/{prof['id']}/homepage", json={"url": "https://jg.example.edu/"})
    run_jobs()
    assert client.get(f"/professors/{prof['id']}").json()["resolve_status"] == "resolved"


def test_evidence_history_when_page_changes(database, monkeypatch):
    import app.services.professors as prof_svc
    from app.main import app

    pages = {"https://hist.example.edu/~kim/": "<p>Kim Lee is a professor. I am recruiting PhD students for Fall 2027.</p>"}

    def fetch(url, check_robots=True):
        return FetchResult(url=url, final_url=url, status_code=200, content_type="text/html", content=pages[url].encode(),
                           last_modified="Wed, 01 Jul 2026 10:00:00 GMT")

    monkeypatch.setattr(prof_svc, "fetch", fetch)
    client = TestClient(app)
    [prof] = client.post("/professors/bulk", json={"entries": [
        {"raw": "k", "name": "Kim Lee", "school_raw": "Example State", "url": "https://hist.example.edu/~kim/"}]}).json()
    run_jobs()
    detail = client.get(f"/professors/{prof['id']}").json()
    assert (detail["recruiting_status"], detail["recruiting_confidence"]) == ("explicitly_recruiting", "high")
    [ev] = detail["evidence"]
    assert ev["source_type"] == "personal" and ev["gone_at"] is None and ev["page_updated_at"].startswith("2026-07-01")

    pages["https://hist.example.edu/~kim/"] = "<p>Kim Lee is a professor working on clinical NLP.</p>"
    client.post(f"/professors/{prof['id']}/refresh")
    run_jobs()
    detail = client.get(f"/professors/{prof['id']}").json()
    assert detail["recruiting_status"] == "unknown" and detail["recruiting_confidence"] is None
    [ev] = detail["evidence"]
    assert ev["gone_at"] is not None  # kept as history, no longer counted


def test_user_submitted_evidence(database, monkeypatch):
    import app.services.professors as prof_svc
    from app.main import app

    pages = {
        "https://sub.example.edu/~ana/": "<p>Ana Ruiz is a professor of clinical NLP.</p>",
        "https://sub.example.edu/~ana/openpositions.html": (
            "<p>I will be recruiting 1-2 PhD students for Fall 2027. Please do not email me about admissions.</p>"),
    }

    def fetch(url, check_robots=True):
        if url not in pages:
            raise RuntimeError("404")
        return FetchResult(url=url, final_url=url, status_code=200, content_type="text/html", content=pages[url].encode())

    monkeypatch.setattr(prof_svc, "fetch", fetch)
    client = TestClient(app)
    [prof] = client.post("/professors/bulk", json={"entries": [
        {"raw": "a", "name": "Ana Ruiz", "school_raw": "Sub State", "url": "https://sub.example.edu/~ana/"}]}).json()
    run_jobs()
    pid = prof["id"]
    assert client.get(f"/professors/{pid}").json()["recruiting_status"] == "unknown"

    url = "https://sub.example.edu/~ana/openpositions.html"
    bad = client.post(f"/professors/{pid}/evidence", json={"url": url, "quote": "I am recruiting 5 students.", "claim": "explicitly_recruiting"})
    assert bad.status_code == 400 and "isn't on the page" in bad.json()["detail"]

    ok = client.post(f"/professors/{pid}/evidence", json={"url": url})  # no quote: read the page
    assert ok.status_code == 200, ok.text
    detail = client.get(f"/professors/{pid}").json()
    assert (detail["recruiting_status"], detail["recruiting_cycle"], detail["recruiting_confidence"]) == (
        "explicitly_recruiting", "Fall 2027", "high")
    assert detail["contact_policy"] == "do_not_email"
    assert {e["extractor"] for e in detail["evidence"]} == {"user"}

    # A re-check keeps the submitted page and its evidence.
    client.post(f"/professors/{pid}/refresh")
    run_jobs()
    detail = client.get(f"/professors/{pid}").json()
    assert detail["recruiting_status"] == "explicitly_recruiting"
    assert all(e["gone_at"] is None for e in detail["evidence"])

    # If the sentence is removed from the page, it moves to history on the next re-check.
    pages[url] = "<p>Our lab studies clinical NLP.</p>"
    client.post(f"/professors/{pid}/refresh")
    run_jobs()
    detail = client.get(f"/professors/{pid}").json()
    assert detail["recruiting_status"] == "unknown" and all(e["gone_at"] for e in detail["evidence"])

    for e in detail["evidence"]:
        assert client.delete(f"/professors/evidence/{e['id']}").status_code == 204
    assert client.get(f"/professors/{pid}").json()["evidence"] == []


def test_directory_profile_explores_linked_personal_site(database, monkeypatch):
    import app.services.professors as prof_svc
    from app.main import app

    pages = {
        "https://directory.dir.example.edu/lee/": '<p>Lee Park, Professor.</p><a href="https://people.dir.example.edu/~lee/">Research Website</a>',
        "https://people.dir.example.edu/~lee/": '<p>I study clinical NLP.</p><a href="join.html">Join</a>',
        "https://people.dir.example.edu/~lee/join.html": "<p>I am recruiting PhD students for Fall 2027.</p>",
    }
    monkeypatch.setattr(prof_svc, "fetch", lambda url, check_robots=True: FetchResult(
        url=url, final_url=url, status_code=200, content_type="text/html", content=pages[url].encode()))
    client = TestClient(app)
    [prof] = client.post("/professors/bulk", json={"entries": [
        {"raw": "l", "name": "Lee Park", "school_raw": "Dir State", "url": "https://directory.dir.example.edu/lee/"}]}).json()
    run_jobs()
    detail = client.get(f"/professors/{prof['id']}").json()
    assert {p["url"] for p in detail["pages"]} == set(pages)
    assert (detail["recruiting_status"], detail["recruiting_cycle"]) == ("explicitly_recruiting", "Fall 2027")
    assert detail["recruiting_source_url"] == "https://people.dir.example.edu/~lee/join.html"


def test_unverified_evidence_from_blocked_site(database, monkeypatch):
    import app.services.professors as prof_svc
    from app.main import app

    home = "https://blk.example.edu/faculty/sam/"

    def fetch(url, check_robots=True):
        if url == home:
            return FetchResult(url=url, final_url=url, status_code=200, content_type="text/html",
                               content=b"<p>Sam Cho is a professor of health AI.</p>")
        raise RuntimeError("Client error '403 Forbidden'")

    monkeypatch.setattr(prof_svc, "fetch", fetch)
    client = TestClient(app)
    [prof] = client.post("/professors/bulk", json={"entries": [{"raw": "s", "name": "Sam Cho", "school_raw": "Blk State", "url": home}]}).json()
    run_jobs()
    pid, blocked = prof["id"], "https://samcho.blk.example.edu/"

    no_quote = client.post(f"/professors/{pid}/evidence", json={"url": blocked})
    assert no_quote.status_code == 400 and "block" in no_quote.json()["detail"]

    ok = client.post(f"/professors/{pid}/evidence", json={
        "url": blocked, "quote": "I am recruiting PhD students for Fall 2027.", "claim": "explicitly_recruiting", "cycle": "Fall 2027"})
    assert ok.status_code == 200, ok.text
    detail = client.get(f"/professors/{pid}").json()
    [ev] = detail["evidence"]
    assert ev["verified"] is False and ev["extractor"] == "user"
    assert (detail["recruiting_status"], detail["recruiting_confidence"]) == ("explicitly_recruiting", "medium")

    client.post(f"/professors/{pid}/refresh")  # still blocked: evidence stays, still unverified
    run_jobs()
    [ev] = client.get(f"/professors/{pid}").json()["evidence"]
    assert ev["gone_at"] is None and ev["verified"] is False


def test_evidence_kept_when_linking_page_fails(database, monkeypatch):
    import app.services.professors as prof_svc
    from app.main import app

    base = "https://flaky.example.edu/~ed/"
    pages = {base: '<a href="people.html">People</a>', base + "people.html": '<a href="openpositions.html">Open Positions</a>',
             base + "openpositions.html": "<p>I do have openings for PhD students in the next admission cycle.</p>"}
    down: set[str] = set()

    def fetch(url, check_robots=True):
        if url in down:
            raise RuntimeError("timed out")
        return FetchResult(url=url, final_url=url, status_code=200, content_type="text/html", content=pages[url].encode())

    monkeypatch.setattr(prof_svc, "fetch", fetch)
    client = TestClient(app)
    [prof] = client.post("/professors/bulk", json={"entries": [{"raw": "e", "name": "Ed Flake", "school_raw": "Flaky U", "url": base}]}).json()
    run_jobs()
    assert client.get(f"/professors/{prof['id']}").json()["recruiting_status"] == "explicitly_recruiting"

    down.add(base + "people.html")  # the page linking to Open Positions times out
    client.post(f"/professors/{prof['id']}/refresh")
    run_jobs()
    detail = client.get(f"/professors/{prof['id']}").json()
    assert detail["recruiting_status"] == "explicitly_recruiting"
    assert all(e["gone_at"] is None for e in detail["evidence"])
