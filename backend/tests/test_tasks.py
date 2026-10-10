from datetime import date, timedelta

from fastapi.testclient import TestClient


def test_outreach_tasks(database):
    from app.main import app

    client = TestClient(app)
    [prof] = client.post("/professors/bulk", json={"entries": [
        {"raw": "x", "name": "Robin Task", "school_raw": "Tufts University"}]}).json()

    soon = (date.today() + timedelta(days=3)).isoformat()
    t = client.post("/outreach-tasks", json={
        "title": "Warm-up task", "professor_id": prof["id"], "due_date": soon,
        "steps": [{"text": "Run inference"}, {"text": "Write post-processing"}],
        "links": [{"label": "Instructions", "url": "https://example.org/warmup"}],
        "notes": "One submission per week.",
    }).json()
    assert t["professor_name"] == "Robin Task" and t["school_name"] == "Tufts University"
    assert [s["done"] for s in t["steps"]] == [False, False] and not t["done"]

    general = client.post("/outreach-tasks", json={"title": "Email the director"}).json()
    assert general["professor_id"] is None and general["professor_name"] is None

    # Ticking a step replaces the step list; the professor filter returns only their tasks.
    steps = [{**t["steps"][0], "done": True}, t["steps"][1]]
    t = client.patch(f"/outreach-tasks/{t['id']}", json={"steps": steps}).json()
    assert [s["done"] for s in t["steps"]] == [True, False]
    assert [x["id"] for x in client.get(f"/outreach-tasks?professor_id={prof['id']}").json()] == [t["id"]]

    # Open tasks come first, soonest due first; done tasks go last.
    assert [x["id"] for x in client.get("/outreach-tasks").json()] == [t["id"], general["id"]]
    client.patch(f"/outreach-tasks/{t['id']}", json={"done": True})
    assert [x["id"] for x in client.get("/outreach-tasks").json()] == [general["id"], t["id"]]

    assert client.delete(f"/outreach-tasks/{general['id']}").status_code == 204
    assert client.patch(f"/outreach-tasks/{general['id']}", json={"done": True}).status_code == 404
