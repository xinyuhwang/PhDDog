import pytest
from fastapi.testclient import TestClient

STATEMENT = "I led a liver tumor segmentation project on multi-phase contrast CT as lead and first author."


@pytest.fixture(autouse=True)
def _clean_profile(database):
    """Later tests (test_flow) expect to start without a profile."""
    yield
    from app.db.models import AdmissionAssessment, School, UserProfile
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        db.query(AdmissionAssessment).delete()
        db.query(UserProfile).delete()
        db.query(School).filter_by(name="Vanderbilt University").update({"is_target": False})
        db.commit()


def _setup(client):
    from app.db.models import Professor
    from app.db.session import SessionLocal

    client.put("/profile", json={"research_statement": STATEMENT, "keywords": ["medical imaging"]})
    school = client.post("/schools", json={"name": "Vanderbilt University", "is_target": True}).json()
    app_row = client.post("/applications", json={"school_id": school["id"], "program": "Computer Science PhD"}).json()
    with SessionLocal() as db:
        if not db.query(Professor).filter_by(school_id=school["id"], normalized_name="yuankai huo").first():
            db.add(Professor(school_id=school["id"], name="Yuankai Huo", normalized_name="yuankai huo"))
            db.commit()
    return school, app_row


def _body(school, app_row, **over):
    return {
        "school_id": school["id"], "application_id": app_row["id"], "rating": "target",
        "summary": "Close fit with a recruiting advisor.",
        "reasons": [
            {"text": "Lead-author imaging work", "kind": "profile",
             "evidence": "liver tumor segmentation project on multi-phase contrast CT"},
            {"text": "Advisor welcomes email", "kind": "faculty", "evidence": "Yuankai Huo asks for a CV by email"},
            {"text": "No publications required", "kind": "program", "evidence": "Publications not required",
             "source_url": "https://example.edu/faq"},
        ],
        "gap": "No accepted paper yet.", "action": "Email Huo with CV.",
    } | over


def test_assessments(database):
    from app.main import app

    client = TestClient(app)
    school, app_row = _setup(client)

    # Listed but not evaluated; offline mode can't run it.
    out = client.get("/assessments").json()
    row = next(r for r in out["rows"] if r["application_id"] == app_row["id"])
    assert out["can_run"] is False and row["rating"] is None
    assert client.post("/assessments/run").status_code == 409

    # Evidence is checked: a quote that isn't in the materials, a professor not saved, a fact without a source.
    bad = _body(school, app_row, reasons=[
        {"text": "x", "kind": "profile", "evidence": "published five MICCAI papers as first author"},
        {"text": "y", "kind": "faculty", "evidence": "Someone Else is recruiting"},
        {"text": "z", "kind": "admit_pattern", "evidence": "Admits had 2 papers"},
    ])
    r = client.put("/assessments", json=bad)
    assert r.status_code == 400 and "#1" in r.text and "#2" in r.text and "#3" in r.text
    assert client.put("/assessments", json=_body(school, app_row, rating="sure_thing")).status_code == 422

    r = client.put("/assessments", json=_body(school, app_row))
    assert r.status_code == 200 and r.json()["assessed_by"] == "claude-session"
    row = next(r for r in client.get("/assessments").json()["rows"] if r["application_id"] == app_row["id"])
    assert row["rating"] == "target" and len(row["reasons"]) == 3 and row["stale"] == []

    # Re-importing replaces it rather than adding a second one.
    client.put("/assessments", json=_body(school, app_row, rating="reach"))
    rows = [r for r in client.get("/assessments").json()["rows"] if r["application_id"] == app_row["id"]]
    assert len(rows) == 1 and rows[0]["rating"] == "reach"

    # Changing the school's admit note, or the profile, marks it stale.
    client.patch(f"/schools/{school['id']}/admit-note", json={"admit_note": "Admits had a master's (source)"})
    row = next(r for r in client.get("/assessments").json()["rows"] if r["application_id"] == app_row["id"])
    assert any("admit notes" in s for s in row["stale"])
    client.put("/profile", json={"research_statement": STATEMENT + " Also clinical NLP.", "keywords": []})
    row = next(r for r in client.get("/assessments").json()["rows"] if r["application_id"] == app_row["id"])
    assert any("materials" in s for s in row["stale"])

    # Unselected schools drop out of the list.
    client.patch(f"/schools/{school['id']}/target", json={"is_target": False})
    assert all(r["school_id"] != school["id"] for r in client.get("/assessments").json()["rows"])


def test_assess_handler_keeps_only_checked_reasons(database, monkeypatch):
    from app.db.models import AdmissionAssessment
    from app.db.session import SessionLocal
    from app.llm.fake import FakeLLM
    from app.llm.schemas import AssessmentOut, AssessmentReason
    from app.main import app
    from app.services import assessments, jobs

    client = TestClient(app)
    school, app_row = _setup(client)
    client.patch(f"/schools/{school['id']}/target", json={"is_target": True})

    def judge(self, profile, materials, programs):
        return [AssessmentOut(rating="reach", summary="s", reasons=[
            AssessmentReason(text="ok", kind="profile", evidence="multi-phase contrast CT as lead and first author"),
            AssessmentReason(text="made up", kind="profile", evidence="won a best paper award at MICCAI"),
        ]) for _ in programs]

    monkeypatch.setattr(FakeLLM, "name", "claude")
    monkeypatch.setattr(FakeLLM, "assess_admission", judge)
    assert client.post("/assessments/run").status_code == 202
    with SessionLocal() as db:
        jobs.run_pending(db)
        row = db.query(AdmissionAssessment).filter_by(application_id=app_row["id"]).one()
        assert row.rating == "reach" and [r["text"] for r in row.reasons] == ["ok"]
    assert assessments.can_run()
