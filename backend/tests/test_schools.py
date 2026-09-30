import pytest

from app.ingest import openalex
from app.ingest.openalex import Institution, resolve_school
from app.services.schools import normalize_domain

NU = [
    Institution("Northwestern University", ["NU"], "northwestern.edu", "US", 339938),
    Institution("Nanjing University", ["NJU", "NU"], "nju.edu.cn", "CN", 211917),
    Institution("Northeastern University", ["NEU", "NU"], "northeastern.edu", "US", 109363),
]
UNC = [
    Institution("University of North Carolina at Chapel Hill", ["UNC"], "unc.edu", "US", 381757),
    Institution("Universidad Nacional de Córdoba", ["UNC"], "unc.edu.ar", "AR", 51254),
]


def test_ambiguous_acronym_asks(monkeypatch):
    monkeypatch.setattr(openalex, "search_institutions", lambda q, limit=8: NU)
    match, suggestions = resolve_school("NU")
    assert match is None
    assert "Northeastern University" in [s.name for s in suggestions]


def test_dominant_acronym_accepted(monkeypatch):
    monkeypatch.setattr(openalex, "search_institutions", lambda q, limit=8: UNC)
    match, _ = resolve_school("UNC")
    assert match.name == "University of North Carolina at Chapel Hill" and match.domain == "unc.edu"


@pytest.mark.parametrize(("raw", "expected"), [
    ("tamu.edu", "tamu.edu"), ("https://www.tamu.edu/", "tamu.edu"), ("www.cs.unc.edu/people", "cs.unc.edu"),
])
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


@pytest.mark.parametrize("bad", ["Texas A&M University", "northeastern university", "tamu"])
def test_normalize_domain_rejects_names(bad):
    with pytest.raises(ValueError):
        normalize_domain(bad)


def test_confirm_merges_into_existing_school(database, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(openalex, "search_institutions", lambda q, limit=8: NU)
    client = TestClient(app)
    client.post("/professors/bulk", json={"entries": [
        {"raw": "a", "name": "Tina Eliassi-Rad", "school_raw": "NU", "url": "https://x.example.edu/"},
        {"raw": "b", "name": "Someone Else", "school_raw": "Northeastern"},
    ]})
    schools = {s["name"]: s for s in client.get("/schools").json()}
    nu = schools["NU"]
    assert not nu["confirmed"] and nu["suggestions"]

    bad = client.post(f"/schools/{nu['id']}/confirm", json={"name": "Northeastern University", "primary_domain": "northeastern university"})
    assert bad.status_code == 400

    ok = client.post(f"/schools/{nu['id']}/confirm", json={"name": "Northeastern University", "primary_domain": "northeastern.edu"}).json()
    assert ok["confirmed"] and "NU" in ok["aliases"]
    names = [s["name"] for s in client.get("/schools").json()]
    assert "NU" not in names
    # "NU" now means Northeastern for this user.
    [entry] = client.post("/professors/parse", json={"text": "Tina Eliassi-Rad, NU"}).json()
    assert "duplicate" in entry["issues"]
