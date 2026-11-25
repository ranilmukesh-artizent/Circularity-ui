"""P9-8.5: a generic mock can page by a `Link` header and by a next URL in the body (sim/generic/spec.py, routes.py).

Each test builds its own tiny mock (schema "paging_test") on the test database and reads it through its router.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from sim.core.db import engine
from sim.generic.routes import build
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import seed

KEY = {"x-api-key": "paging_test-demo-key"}


def _spec(paging: Paging) -> Spec:
    return Spec(
        source_id="paging_test",
        title="Paging test",
        schema="paging_test",
        base_path="/paging/api",
        auth=Auth("api_key", header="x-api-key"),
        paging=paging,
        resources=(Resource("things", "/things", id_field="thingId"),),
        seed=lambda s: {"things": [{"thingId": f"T{i:02d}"} for i in range(7)]},  # noqa: ARG005
    )


@pytest.fixture
def served():
    made: list[TestClient] = []

    def make(paging: Paging) -> TestClient:
        mock = build(_spec(paging))
        with engine.begin() as conn:
            mock.reset(conn, seed())
        app = FastAPI()
        assert mock.router is not None
        app.include_router(mock.router)
        made.append(TestClient(app))
        return made[-1]

    yield make
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA IF EXISTS "paging_test" CASCADE'))


def test_header_link_pages_by_link_header(served):
    c = served(Paging("header_link", items_key="data", next_key=None, total_key="total"))
    seen: list[str] = []
    url: str | None = "/paging/api/things?limit=3"
    for _ in range(10):
        r = c.get(url, headers=KEY)
        assert r.status_code == 200, r.text
        assert "next" not in r.json()
        seen += [d["thingId"] for d in r.json()["data"]]
        link = r.headers.get("link")
        if not link:
            break
        url = link.split(">")[0].lstrip("<")
        assert 'rel="next"' in link
    assert seen == [f"T{i:02d}" for i in range(7)]


def test_json_link_pages_by_nested_next_url(served):
    c = served(Paging("json_link", items_key="data", next_key="meta.next", total_key=None))
    seen: list[str] = []
    url: str | None = "/paging/api/things?limit=3"
    pages = 0
    while url:
        r = c.get(url, headers=KEY)
        body = r.json()
        seen += [d["thingId"] for d in body["data"]]
        url = body["meta"]["next"]
        pages += 1
        assert pages < 10
    assert pages == 3 and len(seen) == 7
