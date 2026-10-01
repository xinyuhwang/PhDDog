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
