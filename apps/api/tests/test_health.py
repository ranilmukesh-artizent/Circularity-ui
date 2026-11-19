from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from di.main import app

client = TestClient(app)


def test_live():
    assert client.get("/api/health/live").json() == {"status": "ok"}


def test_health_reports_database_migration():
    body = client.get("/api/health").json()
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert body["checks"]["database"] == {"ok": True, "migration": head}
    assert "source_sim" in body["checks"]  # reachable in compose, may be down in isolated test runs
