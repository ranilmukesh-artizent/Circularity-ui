"""B5: the same contract test for every generic mock spec (sim/generic/specs/*). A new spec is tested automatically."""

import base64
import importlib
import pkgutil

import pytest
from fastapi.testclient import TestClient

import sim.generic.specs as specs_pkg
from sim.core.registry import BY_SOURCE_ID, CATALOG_BY_ID
from sim.generic.spec import Spec, credentials
from sim.main import app
from sim.seed import seed

_MODULES = [importlib.import_module(f"sim.generic.specs.{m.name}") for m in pkgutil.iter_modules(specs_pkg.__path__)]
SPECS: list[Spec] = [m.SPEC for m in _MODULES if hasattr(m, "SPEC")]  # the sandbox is a hand-written MOCK


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def headers(client, spec: Spec) -> dict:
    c, a = credentials(spec), spec.auth
    if a.kind == "api_key":
        return {a.header: c["api_key"]}
    if a.kind == "bearer":
        return {"Authorization": "Bearer " + c["api_key"]}
    if a.kind == "basic":
        return {"Authorization": "Basic " + base64.b64encode(f"{c['user']}:{c['password']}".encode()).decode()}
    tok = client.post(
        spec.base_path + a.token_path, data={"grant_type": "client_credentials"}, auth=(c["client_id"], c["client_secret"])
    )
    assert tok.status_code == 200, tok.text
    return {"Authorization": "Bearer " + tok.json()["access_token"]}


def list_all(client, spec: Spec, path: str, h: dict, params: dict | None = None) -> list[dict]:
    p, out, q = spec.paging, [], dict(params or {})
    q[p.size_param if p.style == "page" else p.limit_param] = 7  # small pages, so paging is exercised
    for _ in range(1000):
        r = client.get(spec.base_path + path, headers=h, params=q)
        assert r.status_code == 200, r.text
        body = r.json()
        out += body[p.items_key]
        nxt = body.get(p.next_key) if p.next_key else None
        if nxt is None:
            if p.total_key:
                assert body[p.total_key] == len(out)
            return out
        q[{"page": p.page_param, "cursor": p.cursor_param, "offset": p.offset_param}[p.style]] = nxt
    raise AssertionError("paging did not end")


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.source_id)
def test_spec_matches_the_registry(spec: Spec):
    sysm = (BY_SOURCE_ID | CATALOG_BY_ID)[spec.source_id]  # a demo source or a catalogue system (plan 6 A3)
    assert (spec.schema, spec.base_path, spec.title) == (sysm.schema, sysm.base_path, sysm.vendor)
    data = spec.seed(seed())
    assert set(data) == {r.name for r in spec.resources}
    for r in spec.resources:
        ids = [d[r.id_field] for d in data[r.name]]
        assert len(ids) == len(set(ids)), f"duplicate ids in {r.name}"


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.source_id)
def test_contract(client, spec: Spec):
    client.post("/_sim/reset", params={"system": spec.source_id}).raise_for_status()
    first = spec.resources[0]
    assert client.get(spec.base_path + first.path).status_code == 401
    h = headers(client, spec)
    data = spec.seed(seed())
    for r in spec.resources:
        items = list_all(client, spec, r.path, h)
        assert len(items) == len(data[r.name]), r.name
        if items:
            one = client.get(f"{spec.base_path}{r.path}/{items[0][r.id_field]}", headers=h)
            assert one.status_code == 200 and one.json() == items[0]
            for f in r.filters:
                v = items[0].get(f)
                if isinstance(v, str):
                    hits = list_all(client, spec, r.path, h, {f: v})
                    assert hits and all(x.get(f) == v for x in hits), (r.name, f)
        assert client.get(f"{spec.base_path}{r.path}/no-such-id", headers=h).status_code == 404
        if r.create:
            made = client.post(spec.base_path + r.path, headers=h, json={"note": "contract test"})
            assert made.status_code == 201, made.text
            new_id = made.json()[r.id_field]
            assert client.post(spec.base_path + r.path, headers=h, json={r.id_field: new_id}).status_code == 409
            delta = client.get(spec.base_path + r.path, headers=h, params={spec.updated_since_param: "2026-10-07T09:00:00Z"})
            assert new_id in [d[r.id_field] for d in delta.json()[spec.paging.items_key]]
            if r.update:
                patched = client.patch(f"{spec.base_path}{r.path}/{new_id}", headers=h, json={"note": "patched"})
                assert patched.status_code == 200 and patched.json()["note"] == "patched"
    assert client.get(spec.base_path + first.path, headers=h, params={"bogus": "1"}).status_code == 400
