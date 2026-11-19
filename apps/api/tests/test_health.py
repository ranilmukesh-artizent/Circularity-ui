from fastapi.testclient import TestClient

from di.main import app

client = TestClient(app)


def test_live():
    assert client.get("/api/health/live").json() == {"status": "ok"}


def test_health_reports_database_migration():
    body = client.get("/api/health").json()
    assert body["checks"]["database"] == {"ok": True, "migration": "0001"}
    assert "source_sim" in body["checks"]  # reachable in compose, may be down in isolated test runs
