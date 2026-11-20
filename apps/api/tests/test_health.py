from alembic.config import Config
from alembic.script import ScriptDirectory

from di.config import get_settings
from di.db import get_session
from di.main import app
from tests.helpers import client


def test_live():
    assert client.get("/api/health/live").json() == {"status": "ok"}


def test_health_reports_database_migration():
    body = client.get("/api/health").json()
    head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    assert body["checks"]["database"] == {"ok": True, "migration": head}
    assert "source_sim" in body["checks"]  # reachable in compose, may be down in isolated test runs


def test_health_hides_exception_text(monkeypatch):
    """A failing check says only that it is unreachable; the exception text goes to the log, not to the client."""

    class Broken:
        def execute(self, *a, **kw):
            raise RuntimeError("password authentication failed for user circ at 10.0.0.5")

    monkeypatch.setattr(get_settings(), "source_sim_url", "http://127.0.0.1:1")
    app.dependency_overrides[get_session] = lambda: Broken()
    try:
        body = client.get("/api/health").json()
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert body == {
        "status": "degraded",
        "checks": {"database": {"ok": False, "error": "unreachable"}, "source_sim": {"ok": False, "error": "unreachable"}},
    }
