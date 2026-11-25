"""Helpers shared by the api tests: one in-process client, signed-in headers per account, the actions call, and the
normalisations used to compare answers with the golden files (fixtures/golden, read with `di.core.golden.load`).

`conftest.py` also offers `client` and `login` as fixtures for tests that prefer them.
"""

from fastapi.testclient import TestClient

from di.main import app
from di.services.engine.jsmath import js_round

client = TestClient(app)
_headers: dict[str, dict] = {}


def h(user: str) -> dict:
    """The Authorization header for `user` (any demo account id), signed in once per test session."""
    if user not in _headers:
        r = client.post("/api/auth/login", json={"username": user, "password": "x"})
        assert r.status_code == 200, r.text
        _headers[user] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _headers[user]


def call(action: str, body: dict, user: str) -> dict:
    """POST /api/actions/{action} as `user`; the JSON answer."""
    return client.post(f"/api/actions/{action}", json=body, headers=h(user)).json()


def publish_seeded_here() -> None:
    """Mark the demo's seeded published workflows as published in the app (their `pub`, as workflow.publish sets it),
    so triggers fire for them (di/workflow/triggers.py published_here); a test of triggers stands in for a person who
    pressed Publish."""
    from di.core import state
    from di.core.db import SessionLocal
    from di.repositories.workflows import all_workflows
    from di.services.actions import workflows as wf

    with SessionLocal() as s:
        for w in all_workflows(s):
            if w.get("status") == "published" and not w.get("pub"):
                w = state.get(s, "workflows", w["id"], for_update=True)
                wf.graph_of(w)
                wf._set_pub(w)
                state.put(s, "workflows", w["id"], w)
        s.commit()


def live_stale_sources() -> list[dict]:
    """The sources the live Connection Fabric shows stale or not connected (the Source Map's list), in its order."""
    srcs = client.get("/api/screens/integration/sources", headers=h("developer")).json()["sources"]
    return [s for s in srcs if s["status"] in ("stale", "unavailable")]


def with_live_source_tasks(items: list[dict], stale: list[dict]) -> list[dict]:
    """A golden task list with its Source-map items (the Developer's stale or unconnected sources: btn "Open Source
    map") replaced by `stale`, the live Connection Fabric's, in the same shape and place (decision-log D-Fabric: the
    Developer's tasks read the live fabric, as the briefing and Home's alerts do). Every other item is the golden one."""
    at = [k for k, x in enumerate(items) if x.get("btn") == "Open Source map"]
    if not at:
        return items
    tpl = items[at[0]]
    title, detail = ("title", "detail") if "title" in tpl else ("t", "d")
    made = [{**tpl, title: f"{s['name']} · {s['status']}", detail: s["vendor"]} for s in stale]
    rest = [x for k, x in enumerate(items) if k not in at]
    return rest[: at[0]] + made + rest[at[0] :]


def with_live_inbox(want: dict, got: dict) -> dict:
    """A golden Developer inbox.get output with its live Connection Fabric parts (decision-log D-Fabric): the
    Source-map items and the briefing's sources line from the live fabric; the briefing's conflicts line as the server
    gave it (Home's briefing test checks its text against the conflict queue); `total` follows the items."""
    stale = live_stale_sources()
    items = with_live_source_tasks(want["items"], stale)
    names = (": " + ", ".join(s["name"] for s in stale)) if stale else ""
    line = {"go": "integration/map", "n": len(stale),
            "text": f"{len(stale)} source{'' if len(stale) == 1 else 's'} stale or not connected{names}."}  # fmt: skip
    briefing = [line if b.get("go") == "integration/map" else b for b in want["briefing"]]
    live_cf = [b for b in got.get("briefing", []) if b.get("go") == "integration/conflicts"]
    briefing = [live_cf[0] if b.get("go") == "integration/conflicts" and live_cf else b for b in briefing]
    return {**want, "items": items, "briefing": briefing, "total": len(items)}


def strict(x):
    """Booleans tagged, so True and 1 differ when two structures are compared with == (JSON and the demo keep them
    apart; Python does not)."""
    if isinstance(x, bool):
        return ("bool", x)
    if isinstance(x, dict):
        return {k: strict(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [strict(v) for v in x]
    return x


def norm(x):
    """The golden dump's normalisation (numbers to 1e-6), with booleans kept strict."""
    if isinstance(x, bool):
        return ("bool", x)
    if isinstance(x, float):
        return js_round(x * 1e6) / 1e6
    if isinstance(x, dict):
        return {k: norm(v) for k, v in x.items()}
    if isinstance(x, list):
        return [norm(v) for v in x]
    return x


LINE_OWNER = "Fleet North America"  # the tool-fleet pack's `owner` (identity): a line owned by another org is refused


FRESH_SEEN = "2026-10-06T08:00:00+00:00"  # telematics last seen a day before the pinned clock (2026-10-07 09:00 UTC)


def tool_case_facts(
    asset_key: str, facts: dict | None = None, *, line: dict | None = None, owner: str = LINE_OWNER,
    seen: str | None = FRESH_SEEN, **over
) -> dict:  # fmt: skip
    """The facts of a tool-fleet case with an active contract line on file (plan 9, P9-3.6, GR-07): the line of the serial
    `asset_key` and its contract are written to the canonical store as the fleet contract system's sync would (fields of
    `line` override the line's: `status`, `return_reason`, `theft_claim_open`, ...; `owner` is its contract's owner org), and
    `facts` (with `over` on top) are returned for the case's intake. Call it after the test's reset, before opening the case.
    The tool's telematics are last seen at `seen` (default: a day before the pinned clock; None: none), so GR-13 passes."""
    from di.core.db import SessionLocal
    from di.services.canonical import store as canonical

    row = {
        "line_id": f"FL-{asset_key}",
        "contract_id": "FC-TEST",
        "serial": asset_key,
        "status": "active",
        "tool_class": (facts or {}).get("cls"),
    } | (line or {})
    facts_ = [canonical.Fact("contract_line", asset_key, k, v, resource="lines") for k, v in row.items() if v is not None]
    facts_.append(canonical.Fact("contract", str(row["contract_id"]), "owner_org", owner, resource="contracts"))
    if seen:  # the tool's telematics (GR-13, P9-3.8)
        facts_.append(canonical.Fact("condition", asset_key, "telemetry_at", seen, resource="tools"))
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts_)
        s.commit()
    return {**(facts or {}), **over}
