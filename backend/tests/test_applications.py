import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient


def test_application_tracker(database):
    from app.main import app

    client = TestClient(app)
    school = client.post("/schools", json={"name": "UCLA"}).json()
    assert school["name"] == "University of California, Los Angeles" and school["is_target"]

    deadline = date.today() + timedelta(days=20)
    a = client.post("/applications", json={"school_id": school["id"], "program": "CS PhD", "deadline": deadline.isoformat(),
                                           "apply_url": "https://grad.ucla.edu/"}).json()
    assert a["total"] == 11 and a["done"] == 0 and a["days_left"] == 20
    # "Ask recommenders" is due 42 days before the deadline: already overdue.
    letters = next(s for s in a["steps"] if s["label"].startswith("Ask recommenders"))
    assert letters["effective_due"] == (deadline - timedelta(days=42)).isoformat()
    assert a["overdue"] >= 2 and a["next_step"]["id"] in {s["id"] for s in a["steps"]}

    client.patch(f"/application-steps/{letters['id']}", json={"done": True})
    a = client.get("/applications").json()[0]
    assert a["done"] == 1 and a["status"] == "in_progress"

    # Moving the deadline moves the default due dates that weren't hand-edited.
    later = deadline + timedelta(days=30)
    a = client.patch(f"/applications/{a['id']}", json={"deadline": later.isoformat()}).json()
    submit = next(s for s in a["steps"] if s["label"] == "Submit the application")
    assert submit["effective_due"] == later.isoformat()

    a = client.post(f"/applications/{a['id']}/steps", json={"label": "Ask Prof. X about rotation"}).json()
    assert a["total"] == 12

    todo = client.get("/applications/todo").json()
    assert todo and all(not t["step"]["done"] for t in todo)
    assert todo == sorted(todo, key=lambda t: t["due"] or "9999")

    client.patch(f"/schools/{school['id']}/target", json={"is_target": False})
    assert not next(s for s in client.get("/schools").json() if s["id"] == school["id"])["is_target"]
    # Unselecting the school hides its steps from "Do next" but keeps the application.
    assert not any(t["application_id"] == a["id"] for t in client.get("/applications/todo").json())
    assert any(x["id"] == a["id"] for x in client.get("/applications").json())


def test_compare(database):
    from app.main import app

    client = TestClient(app)
    school = client.post("/schools", json={"name": "Tufts University"}).json()
    a = client.post("/applications", json={"school_id": school["id"], "program": "Computer Science PhD"}).json()
    client.post("/professors/bulk", json={"entries": [
        {"raw": "x", "name": "Pat Kim", "school_raw": "Tufts University", "department_raw": "Computer Science"}]})
    [row] = [r for r in client.get("/compare").json() if r["id"] == a["id"]]
    assert row["program_type"] == "Computer Science" and row["n_faculty"] == 1 and row["n_in_program"] == 1
    assert row["decision"] == "undecided" and row["assessment_by"] is None

    r = client.patch(f"/applications/{a['id']}", json={"fit_score": 4, "tier": "target", "decision": "top8"}).json()
    [row] = [x for x in client.get("/compare").json() if x["id"] == a["id"]]
    assert (row["fit_score"], row["tier"], row["decision"], row["assessment_by"]) == (4, "target", "top8", "user")
    assert client.patch(f"/applications/{a['id']}", json={"fit_score": 9}).status_code == 400

    # Dropping a program on Compare takes its steps out of "Do next" but keeps the application.
    assert any(t["application_id"] == a["id"] for t in client.get("/applications/todo?limit=500").json())
    client.patch(f"/applications/{a['id']}", json={"decision": "drop"})
    assert not any(t["application_id"] == a["id"] for t in client.get("/applications/todo?limit=500").json())
    assert next(x for x in client.get("/applications").json() if x["id"] == a["id"])["decision"] == "drop"


def test_compare_rank_puts_best_fit_and_chance_first():
    from app.api.applications import CompareRow, compare_rank

    def row(name, fit, chance, decision="undecided"):
        return CompareRow(
            id=uuid.uuid4(), school_id=uuid.uuid4(), school_name=name, program="CS PhD", program_type="Computer Science",
            deadline=None, days_left=None, status="planning", fit_score=fit, tier=None, chance=chance, reason=None,
            gaps=None, decision=decision, assessment_by=None, faculty=[], n_faculty=0, n_in_program=0, n_recruiting=0,
            n_target_cycle=0, n_not_recruiting=0,
        )

    rows = [row("Reach fit 5", 5, "reach"), row("Likely fit 4", 4, "likely"), row("Target fit 4", 4, "target"),
            row("Long shot fit 5", 5, "long_shot"), row("Unrated", None, None), row("Dropped", 5, "likely", "drop")]
    # 4+4=8, 4+3=7, 5+2=7 (tie: better fit first), 5+1=6, 0, then dropped.
    assert [r.school_name for r in sorted(rows, key=compare_rank)] == [
        "Likely fit 4", "Reach fit 5", "Target fit 4", "Long shot fit 5", "Unrated", "Dropped"]
