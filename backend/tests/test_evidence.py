"""Status / confidence rules and evidence history (app/services/evidence.py)."""

from datetime import UTC, datetime, timedelta

from app.db.models import Evidence
from app.services.evidence import classify_source, page_updated_at, summarize

NOW = datetime(2026, 9, 30, tzinfo=UTC)


def ev(claim, cycle=None, source_type="personal", kind="recruiting", gone=False, days_ago=0):
    return Evidence(kind=kind, claim=claim, cycle=cycle, quote=f"{claim} {cycle}", source_url="https://x", source_type=source_type,
                    last_seen_at=NOW - timedelta(days=days_ago), gone_at=NOW if gone else None)


def test_no_evidence_is_unknown_not_no():
    s = summarize([], "Fall 2027")
    assert (s.recruiting_status, s.recruiting_confidence, s.contact_policy) == ("unknown", None, "unknown")


def test_target_cycle_on_own_page_is_high():
    s = summarize([ev("explicitly_recruiting", "Fall 2027")], "Fall 2027")
    assert (s.recruiting_status, s.recruiting_confidence, s.recruiting_stale) == ("explicitly_recruiting", "high", False)


def test_earlier_cycle_is_stale_and_low():
    s = summarize([ev("explicitly_recruiting", "Fall 2026")], "Fall 2027")
    assert s.recruiting_stale and s.recruiting_confidence == "low"


def test_every_year_statement_is_medium():
    assert summarize([ev("recruits_generally")], "Fall 2027").recruiting_confidence == "medium"


def test_department_page_alone_is_low():
    assert summarize([ev("explicitly_recruiting", "Fall 2027", source_type="department")], "Fall 2027").recruiting_confidence == "low"


def test_current_cycle_beats_undated_and_older():
    s = summarize([ev("recruits_generally"), ev("explicitly_recruiting", "Fall 2026"), ev("not_recruiting", "Fall 2027")], "Fall 2027")
    assert (s.recruiting_status, s.recruiting_cycle) == ("not_recruiting", "Fall 2027")


def test_gone_evidence_is_ignored():
    assert summarize([ev("explicitly_recruiting", "Fall 2027", gone=True)], "Fall 2027").recruiting_status == "unknown"


def test_contact_policy_most_restrictive_own_page_wins():
    s = summarize([
        ev("welcomes_email", kind="contact_policy"),
        ev("do_not_email", kind="contact_policy"),
        ev("do_not_email", kind="contact_policy", source_type="department"),
    ], "Fall 2027")
    assert s.contact_policy == "do_not_email" and s.contact.source_type == "personal"


def test_classify_source():
    assert classify_source("https://jd.github.io/", "homepage", "x.edu") == "personal"
    assert classify_source("https://www.cs.x.edu/faculty/jane-doe/", "homepage", "x.edu") == "faculty_profile"
    assert classify_source("https://jd.cs.x.edu/lab/", "subpage", "x.edu") == "lab"
    assert classify_source("https://janedoe.org", "linked_site", "x.edu") == "personal"


def test_page_updated_at():
    assert page_updated_at(None, "Last updated: March 3, 2026").date().isoformat() == "2026-03-03"
    assert page_updated_at("Wed, 01 Jul 2026 10:00:00 GMT", "no date here").date().isoformat() == "2026-07-01"
    assert page_updated_at(None, "nothing") is None
