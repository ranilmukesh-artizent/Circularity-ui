"""Plan 9, P9-5.5 (story CR-05): an approved refresh proposal is sent, its lines are drafted and its units reserved.

A person's approval of a contract refresh (`decision.approve`, or `decision.override` for a route that is not the recommendation)
turns the chosen route into the existing execution plan: `propsend`, `propdraft` and `propreserve` (`execution/steps.py`), sent in
order by the instruction queue, each by a writer of `instructions/writers_fleet.py`. Sending the proposal to the customer,
drafting the contract lines and holding the units happen only then (GR-C2): `decision.submit` sends nothing, the standing
policy never approves a proposal, and an agent cannot approve one (`decision.approve` is already in FORBIDDEN_ACTIONS, so no
new action joins it). The writers are driven with a fake client (no source-sim call); the mock's own side is
source-sim/tests/test_fleet_proposals.py.

No model step (R16): the proposal document is the computed pricing (fees, credits, renewal likelihood) and the matched units, so
there is no `AgentLoop` and no model test; nothing a model could word is sent to the customer.

It starts and ends with the demo reset.
"""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from di.core import policy
from di.core.config import get_settings
from di.core.db import SessionLocal
from di.repositories import unit_reservations
from di.services import refresh_decision
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.agents.forbidden import forbidden
from di.services.cases import store
from di.services.execution.steps import STEP_TPL
from di.services.instructions import queue, writers
from tests.helpers import call, client, h
from tests.test_cr_tool_action import ORG, refresh_case  # noqa: F401 - the fixture: FC-30140, one swap and one keep, US

FLEET = "/fleet/api/v1"
PARTS = "/parts/api"
UNITS = [("RU-7001", 58, "A"), ("RU-7002", 70, "A")]


class Mock:
    """The fleet contract system's proposals and draft lines, and the parts system's refurbished units."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.posts: list[tuple[str, dict]] = []
        self.patches: list[tuple[str, dict]] = []
        for u, _, _ in UNITS:
            self.docs[f"{PARTS}/refurbished-units/{u}"] = {"unitId": u, "status": "available"}

    def get_json(self, path, params=None):
        from di.connectors.http import SourceError

        if path not in self.docs:
            raise SourceError("client", f"{path} not found", status=404)
        return self.docs[path]

    def request(self, method, path, json=None, **_):
        body = dict(json or {})
        if method == "POST":
            self.docs[f"{path}/{body.get('proposalId') or body['draftLineId']}"] = body
            self.posts.append((path, body))
        else:
            self.docs[path] |= body
            self.patches.append((path, body))
        return SimpleNamespace(json=lambda: body)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def sending(monkeypatch):
    """Instructions on for the test (the suite turns them off), so an approval queues its first step."""
    monkeypatch.setattr(get_settings(), "instructions", True)


@pytest.fixture
def world(refresh_case, monkeypatch):  # noqa: F811 - the imported fixture, used by name
    monkeypatch.setattr(
        unit_reservations, "stock", lambda s: [{"id": u, "cls": "CMH", "rul": r, "grade": g} for u, r, g in UNITS]
    )
    mock = Mock()
    monkeypatch.setattr(writers, "client", lambda *_: mock)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM unit_reservation WHERE org_unit_id = :o"), {"o": ORG})
        s.commit()
    yield refresh_case, mock
    with SessionLocal() as s:
        s.execute(text("DELETE FROM unit_reservation WHERE org_unit_id = :o"), {"o": ORG})
        s.commit()


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _held(cid: str | None = None) -> list[str]:
    """The unit ids held now: this case's, or everyone's."""
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT unit_id FROM unit_reservation WHERE status = 'held' AND (CAST(:c AS text) IS NULL OR case_id = :c)"),
            {"c": cid},
        ).scalars()
        return sorted(rows)


def _submit(cid: str) -> dict:
    out = call("decision.submit", {"case_id": cid}, "admin")
    assert out["ok"], out
    return _case(cid)


def _approve(cid: str, route: str = "proposal", user: str = "approver") -> dict:
    """A person approves the route (the recommendation, else an override) as the maker-checker pair the pipeline asks for."""
    c = _case(cid)
    r = next(x for x in c["routes"] if x["id"] == route)
    body = {"case_id": cid, "reviewed": True, "rationale": "Refresh proposal reviewed.", "route": r["plan"]}
    return call("decision.approve" if c["recommendation"]["id"] == route else "decision.override", body, user)


def _drive(cid: str) -> list[str]:
    """Send each queued step through its writer and acknowledge it with the system's reference, as the events do."""
    sent: list[str] = []
    for _ in range(5):
        with SessionLocal() as s:
            rows = [r for r in queue.for_case(s, cid) if r["status"] == "queued"]
        if not rows:
            return sent
        ins = rows[-1]
        with SessionLocal() as s:
            c = store.get(s, cid)
            assert c is not None
            prev = {r["kind"]: {"detail": r["detail"]} for r in queue.for_case(s, cid) if r["step"] < ins["step"]}
            try:
                out = writers.WRITERS[writers.write_kind(c, ins["kind"])](s, ins, c, prev)
            except writers.Refused:
                s.commit()  # as `send` does: what the writer recorded stays
                raise
            s.execute(
                text("UPDATE instruction SET status = 'sent', detail = detail || CAST(:d AS jsonb) WHERE id = :i"),
                {"d": json.dumps(out.detail), "i": ins["id"]},
            )
            ack = {"case_id": cid, "step": ins["step"], "ref": out.doc_ref}
            r = invoke("adapter.acknowledge", ack, CallContext(actor=SYSTEM, session=s))
            assert r["ok"], r
            s.commit()
        sent.append(ins["kind"])
    return sent


# ------------------------------------------------------------------ the plan
def test_cr_05_the_routes_have_their_plans():
    assert STEP_TPL["proposal"] == ["propsend", "propdraft", "propreserve"]
    assert STEP_TPL["renew_as_is"] == ["propsend", "propdraft"]
    assert STEP_TPL["upgrade_all"] == ["propsend", "propdraft", "propreserve"]


def test_cr_05_submit_makes_the_priced_routes_the_decision(world):
    cid, _ = world
    c = _submit(cid)
    assert c["stage"] == "awaiting_approval" and c["submitted"]
    assert {r["id"] for r in c["routes"]} == {"proposal", "renew_as_is", "upgrade_all"}
    assert c["approvalHolds"][0]["id"] in ("GR-C1", "GR-C2")  # a person approves; policy never does


# ------------------------------------------------------------------ approval sends, drafts and reserves
def test_cr_05_approval_sends_drafts_reserves(world):
    cid, mock = world
    _submit(cid)
    out = _approve(cid)
    assert out["ok"], out
    c = _case(cid)
    assert [s["k"] for s in c["exec"]["steps"]] == ["propsend", "propdraft", "propreserve"]
    assert _drive(cid) == ["propsend", "propdraft", "propreserve"]
    sent = [d for p, d in mock.posts if p == f"{FLEET}/proposals"]
    assert len(sent) == 1 and sent[0]["contractId"] == "FC-30140" and sent[0]["validUntil"]
    assert sent[0]["proposalId"].startswith("PR-") and sent[0]["feeMonthProposed"] < sent[0]["feeMonthCurrent"]
    drafts = [d for p, d in mock.posts if p == f"{FLEET}/draft-lines"]
    assert {d["serial"] for d in drafts} == {"FC-30140-S00", "FC-30140-S01"}
    assert all(d["proposalId"] == sent[0]["proposalId"] and d["draftLineId"].startswith("DL-") for d in drafts)
    (unit,) = refresh_decision.units_of(c)  # the one swap holds the unit matched at submit; the stock unit reads reserved
    other = next(u for u, _, _ in UNITS if u != unit)
    assert _held(cid) == [unit]
    assert mock.docs[f"{PARTS}/refurbished-units/{unit}"]["status"] == "reserved"
    assert mock.docs[f"{PARTS}/refurbished-units/{other}"]["status"] == "available"


def test_cr_05_a_send_twice_makes_one_proposal(world):
    cid, mock = world
    _submit(cid)
    assert _approve(cid)["ok"]
    _drive(cid)
    with SessionLocal() as s:
        c = store.get(s, cid)
        assert c is not None
        ins = next(r for r in queue.for_case(s, cid) if r["kind"] == "propsend")
        again = writers.WRITERS[writers.write_kind(c, "propsend")](s, ins, c, {})
    assert again.detail["duplicate"] is True
    assert len([1 for p, _ in mock.posts if p == f"{FLEET}/proposals"]) == 1


def test_cr_05_nothing_goes_out_before_approval(world):
    cid, mock = world
    _submit(cid)
    assert mock.posts == [] and mock.patches == []
    assert _held(cid) == []
    with SessionLocal() as s:
        assert queue.for_case(s, cid) == []


def test_cr_05_renew_as_is_sends_and_drafts_but_reserves_nothing(world):
    cid, mock = world
    _submit(cid)
    assert _approve(cid, "renew_as_is")["ok"]
    assert _drive(cid) == ["propsend", "propdraft"]
    assert _held(cid) == [] and mock.patches == []
    assert {d["action"] for p, d in mock.posts if p == f"{FLEET}/draft-lines"} == {"keep"}


def test_cr_05_rejection_releases_nothing(world):
    cid, mock = world
    _submit(cid)
    r = call("decision.decline", {"case_id": cid, "reason": "The customer wants another price."}, "approver")
    assert r["ok"], r
    assert mock.posts == [] and _held(cid) == [] and _case(cid)["stage"] == "reeval"


def test_cr_05_policy_never_approves_proposal(world):
    cid, _ = world
    body = {
        "pack": "tool_fleet",
        "org_unit_id": ORG,
        "name": "Tool returns standing",
        "rules": {"max_value": 20000, "min_confidence": 0.75},
        "owner": "admin",
    }
    saved = call("standingPolicy.save", body, "admin")
    assert saved["ok"], saved
    pid = saved["output"]["id"]
    assert call("standingPolicy.submit", {"id": pid}, "admin")["ok"]
    assert call("standingPolicy.approve", {"id": pid}, "approver")["ok"]
    c = _submit(cid)
    assert c["stage"] == "awaiting_approval" and not c.get("approval")


# ------------------------------------------------------------------ security (R21)
def test_refresh_proposal_maker_cannot_approve(world):
    cid, mock = world
    _submit(cid)  # submitted by admin
    r = _approve(cid, user="admin")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope" and "another person must approve" in r["error"]["message"]
    assert mock.posts == []


def test_refresh_proposal_agent_cannot_approve(world):
    cid, mock = world
    _submit(cid)
    assert forbidden("decision.approve") and forbidden("decision.override")
    agent = {"id": "ext-refresh", "name": "Refresh helper", "tools": ["request_missing_evidence"], "autonomy": "act"}
    assert call("agent.register", agent, "admin")["ok"]
    hdr = h("approver") | {"X-Circularity-Preparer": agent["id"], "X-Circularity-Confirmed": "true"}
    c = _case(cid)
    body = {"case_id": cid, "reviewed": True, "rationale": "Refresh proposal reviewed.", "route": c["recommendation"]["plan"]}
    r = client.post("/api/actions/decision.approve", json=body, headers=hdr).json()
    assert r["ok"] is False and r["error"]["code"] == "approval_required", r
    assert mock.posts == [] and _case(cid)["stage"] == "awaiting_approval"


def test_refresh_proposal_tenant_boundary(world, monkeypatch):
    """An Approver is not tenant-scoped by default, so the account is made not to reach the org (the pipeline's step 5, before the
    approval's own guards and before anything is queued)."""
    cid, mock = world
    _submit(cid)
    ok = policy.tenant_ok
    monkeypatch.setattr(policy, "tenant_ok", lambda a, tenant, ctx=None: tenant != ORG and ok(a, tenant, ctx))
    r = _approve(cid)
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
    assert mock.posts == [] and _case(cid)["stage"] == "awaiting_approval"
    with SessionLocal() as s:
        assert queue.for_case(s, cid) == []


# ------------------------------------------------------------------ a unit taken meanwhile
def test_cr_05_reservation_race_replans(world):
    cid, mock = world
    (unit,) = refresh_decision.units_of(_submit(cid))
    other = next(u for u, _, _ in UNITS if u != unit)
    with SessionLocal() as s:  # another approval holds the unit between this one's submit and approve
        unit_reservations.hold(s, unit, "RF-OTHER", "RF-OTHER:S1", "approver", ORG)
        s.commit()
    assert _approve(cid)["ok"]  # the approval is of what was submitted: the unit that is gone
    assert _drive_until_refused(cid)  # the proposal and its lines went out; the reserve step is refused with conflict
    assert _held(cid) == [] and unit in _held()  # nothing of this case is held; the other case keeps the unit
    assert mock.docs[f"{PARTS}/refurbished-units/{unit}"]["status"] == "available"
    c = _case(cid)
    assert c["stage"] == "reeval" and c["refreshBack"]["to"] == "Fleet desk" and unit in c["refreshBack"]["reason"]
    out = call("case.reevaluate", {"case_id": cid}, "admin")  # the case re-plans: the next unit is proposed
    assert out["ok"], out
    c = _case(cid)
    assert c["stage"] == "awaiting_approval" and refresh_decision.units_of(c) == [other] and "refreshBack" not in c


def _drive_until_refused(cid: str) -> bool:
    try:
        _drive(cid)
    except writers.Refused:
        return True
    return False
