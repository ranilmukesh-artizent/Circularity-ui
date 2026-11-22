import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

# Tests drive the scheduler and the webhook sender themselves (sim.scheduler.tick, sim.webhooks.deliver),
# so the background loops stay off in the app instances that tests start.
os.environ.setdefault("SIM_BACKGROUND", "false")

# Tests get their own database, `sources_test` on the same server, so the running service (which keeps `sources`,
# its background loops and di's webhook subscription) and the tests never touch each other's rows. This runs before
# anything imports `sim.db` (it builds its engine from the setting at import; sim.config only reads it, uncached
# here). The app's start-up (each test module's TestClient) creates the schemas and loads the seed, as it does for
# the live database.
from sim.core.config import Settings

_live = make_url(Settings().database_url)
_test = _live.set(database="sources_test")
_server = create_engine(_live.set(database="postgres"), isolation_level="AUTOCOMMIT")
with _server.connect() as _conn:
    if not _conn.execute(text("SELECT 1 FROM pg_database WHERE datname = 'sources_test'")).scalar():
        _conn.execute(text('CREATE DATABASE "sources_test"'))
_server.dispose()
os.environ["SIM_DATABASE_URL"] = _test.render_as_string(hide_password=False)
