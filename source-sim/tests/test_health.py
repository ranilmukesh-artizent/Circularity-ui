from fastapi.testclient import TestClient

from sim.main import app


def test_health_creates_one_schema_per_system():
    with TestClient(app) as client:  # runs the lifespan (schema creation)
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["missing_schemas"] == []
    assert body["systems"] == 21
