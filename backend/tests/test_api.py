import os

os.environ["DATABASE_URL"] = "sqlite:///./test_catalogforge.db"

from fastapi.testclient import TestClient

from app.main import app
from app.seed import seed

seed()
client = TestClient(app)
API = "/api/v1"


def auth(email: str = "admin@catalogforge.demo") -> dict[str, str]:
    response = client.post(f"{API}/auth/login", json={"email": email, "password": "DemoPass123!"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health_and_login():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["demo_mode"] is True
    assert health.json()["organizations"] == 3
    headers = auth()
    me = client.get(f"{API}/auth/me", headers=headers)
    assert me.status_code == 200
    assert len(me.json()["workspaces"]) == 3


def test_demo_intake_and_duplicate_resolution():
    jobs = client.get(f"{API}/intake/jobs")
    assert jobs.status_code == 200
    assert jobs.json()["total"] >= 20  # organization-scoped, not a cross-tenant aggregate
    duplicates = client.get(f"{API}/duplicates")
    assert duplicates.status_code == 200
    group_id = duplicates.json()["items"][0]["id"]
    separated = client.post(f"{API}/duplicates/{group_id}/separate", json={"rationale": "Test reviewer verified distinct pack sizes."})
    assert separated.status_code == 200
    assert separated.json()["status"] == "Not duplicate"
