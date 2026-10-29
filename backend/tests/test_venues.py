from fastapi.testclient import TestClient


def test_venues(database):
    from app.main import app

    client = TestClient(app)
    a = client.post("/venues", json={"name": "Venue B", "rank": 2, "kind": "journal", "deadline_text": "rolling"}).json()
    b = client.post("/venues", json={
        "name": "Venue A", "rank": 1, "deadline": "2027-03-01", "why": "Fits",
        "links": [{"label": "CFP", "url": "https://example.org/cfp"}],
    }).json()
    assert b["status"] == "considering" and b["links"][0]["label"] == "CFP"

    # Listed by rank.
    names = [v["name"] for v in client.get("/venues").json() if v["name"].startswith("Venue ")]
    assert names == ["Venue A", "Venue B"]

    v = client.patch(f"/venues/{a['id']}", json={"status": "target", "rank": 0}).json()
    assert v["status"] == "target" and v["rank"] == 0
    assert client.patch(f"/venues/{a['id']}", json={"status": "maybe"}).status_code == 422
    assert client.post("/venues", json={"name": "X", "kind": "blog"}).status_code == 422

    assert client.delete(f"/venues/{b['id']}").status_code == 204
    assert client.patch(f"/venues/{b['id']}", json={"rank": 3}).status_code == 404
