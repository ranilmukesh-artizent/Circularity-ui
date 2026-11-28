"""Plan 9, P9-3.17 (story TF-10): an approved tool-fleet decision is carried out by the executing systems and its outcome checked.

A re-issue (`release`) goes to the fleet contract system (its `lease` step PATCHes the contract line of the named renewal with
the issued serial) and a harvest to the parts system (its `partsxfer` step posts each certified part to its open repair order).
Both are steps of the existing execution plan, sent by the instruction queue in order: only the system of a step changes per
template, and an industrial case keeps the demo's systems. When Finance confirms the outcome, a variance above the pack's
tolerance (10% of the predicted net or $50, whichever is larger) opens a task for Finance (I-20) and the case closes either way.

No model step (R16): the plan, the writes and the tolerance are computed, so there is no model test. No new action, so nothing
joins FORBIDDEN_ACTIONS: a person (or the standing policy) approves and Finance confirms, and the test below asserts that
agents still cannot. The writers are driven with a fake client (no source-sim call); the mock's own side is
source-sim/tests/test_fleet_parts_write.py.

It starts and ends with the demo reset.
"""

import pytest
from sqlalchemy import text

from di.core.config import get_settings
from di.core.db import SessionLocal
from di.services.agents.forbidden import forbidden
from di.services.execution import variance
from di.services.execution.steps import steps_for
from di.services.instructions import queue, writers, writers_fleet
from tests import starting

BASE = ""  # the writers' paths are relative to the adapter's base path (writers.client adds /fleet/api/v1)
PARTS = ""
SERIAL = "CMH-48213"
RELEASE = {"id": "release", "dest": {"kind": "lease", "id": "FC-30117-R"}}
HARVEST = {"id": "harvest", "dest": {"kind": "wo", "id": "RO-1, RO-2", "wos": ["RO-1", "RO-2"]}}


def _case(route: dict) -> dict:
    return {
        "id": "RT-TF10",
        "owner": "workspace",
        "template": "tool_fleet",
        "assetId": SERIAL,
        "chosen": route,
        "recommendation": route,
    }


class Fake:
    """The two mocks' documents, read with get_json and written with PATCH."""

    def __init__(self):
        self.docs = {
            f"{BASE}/renewals/FC-30117-R": {"demandId": "FC-30117-R", "contractId": "FC-30117", "toolClass": "CMH"},
            f"{BASE}/contract-lines/FL-30117-03": {
                "lineId": "FL-30117-03",
                "serial": SERIAL,
                "toolClass": "CMH",
                "status": "returned",
            },
            f"{BASE}/contract-lines/FL-30117-05": {
                "lineId": "FL-30117-05",
                "serial": "CMH-11111",
                "toolClass": "CMH",
                "status": "active",
            },
            f"{PARTS}/repair-orders/open/RO-1": {"roId": "RO-1", "partName": "Motor armature"},
            f"{PARTS}/repair-orders/open/RO-2": {"roId": "RO-2", "partName": "Gearbox"},
        }
        self.patches: list[tuple[str, dict]] = []

    def get_json(self, path, params=None):
        if path == f"{BASE}/contract-lines":
            rows = [d for p, d in self.docs.items() if p.startswith(path + "/")]
            return {"items": [d for d in rows if (params or {}).get("contractId", "FC-30117") == "FC-30117"], "next": None}
        return self.docs[path]

    def request(self, method, path, json=None, **_):
        assert method == "PATCH"
        self.patches.append((path, json))
        self.docs[path] = self.docs[path] | json
        return None

    def close(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(writers, "client", lambda *_: f)
    return f


@pytest.fixture(autouse=True)
def world():
    starting.reset()
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item WHERE case_id = 'RT-TF10'"))
        s.commit()
    starting.reset()


def _ins(kind: str) -> dict:
    return {"idem_key": f"APR-1.3.{kind}", "kind": kind, "step": 3}


# ------------------------------------------------------------------ the plan names the executing system
def test_tf_10_steps_name_the_fleet_and_parts_systems():
    rel = {s["k"]: s["sys"] for s in steps_for({"id": "release"}, template="tool_fleet")}
    assert rel["lease"].startswith("Fleet contract system") and rel["repair"] == "MRO · Depot repair"
    har = {s["k"]: s["sys"] for s in steps_for({"id": "harvest"}, template="tool_fleet")}
    assert har["partsxfer"].startswith("Parts and service system")
    assert steps_for({"id": "release"})[3]["sys"] == "Lease · contract"  # an industrial case keeps the demo's systems
    assert queue.template_system("tool_fleet", "lease") == "fleet" and queue.template_system("tool_fleet", "partsxfer") == "parts"
    assert queue.template_system(None, "lease") is None
    # P9-5.5 added a refresh's three steps: proposal and draft lines go to the fleet system, the unit holds to the parts system
    assert writers.operations("fleet") == ["lease", "propsend", "propdraft"]
    assert writers.operations("parts") == ["partsxfer", "propreserve"]


def test_tf_10_the_writer_of_a_step_follows_its_template():
    assert writers.write_kind(_case(RELEASE), "lease") == "fleet_issue"
    assert writers.write_kind(_case(HARVEST), "partsxfer") == "parts_issue"
    assert writers.write_kind({"template": "industrial"}, "lease") == "lease"
    assert writers.WRITERS["fleet_issue"] is writers_fleet.fleet_issue


# ------------------------------------------------------------------ the writes
def test_tf_10_release_writes_fleet_line(fake):
    with SessionLocal() as s:
        sent = writers_fleet.fleet_issue(s, _ins("fleet_issue"), _case(RELEASE), {})
    assert sent.doc_ref == "FL-30117-03"
    ((path, body),) = fake.patches
    assert path == f"{BASE}/contract-lines/FL-30117-03"
    assert body["status"] == "issued" and body["issuedSerial"] == SERIAL and body["issuedKey"] == "APR-1.3.fleet_issue"
    with SessionLocal() as s:  # a resend: the line is issued already, nothing is written twice
        again = writers_fleet.fleet_issue(s, _ins("fleet_issue"), _case(RELEASE), {})
    assert len(fake.patches) == 1 and again.detail["duplicate"] is True


def test_tf_10_release_url_names_the_fleet_base_once(fake, monkeypatch):
    # The real client already ends in the adapter's base path: the writer's path must not repeat it (a doubled
    # /fleet/api/v1/fleet/api/v1 made every lease step fail with a 404, smoke-p9-3 step 14).
    monkeypatch.undo()
    with SessionLocal() as s:
        real = writers.client(s, "fleet")
        parts = writers.client(s, "parts")
        try:
            sim = get_settings().source_sim_url.rstrip("/")
            monkeypatch.setattr(writers, "client", lambda *_: fake)
            writers_fleet.fleet_issue(s, _ins("fleet_issue"), _case(RELEASE), {})
            writers_fleet.parts_issue(s, _ins("parts_issue"), _case(HARVEST), {})
            urls = [(parts if p.startswith("/repair-orders") else real).url(p) for p, _ in fake.patches]
        finally:
            real.close()
            parts.close()
    assert urls == [
        f"{sim}/fleet/api/v1/contract-lines/FL-30117-03",
        f"{sim}/parts/api/repair-orders/open/RO-1",
        f"{sim}/parts/api/repair-orders/open/RO-2",
    ]


def test_tf_10_release_without_a_returned_line_is_refused(fake):
    fake.docs[f"{BASE}/contract-lines/FL-30117-03"]["status"] = "active"
    with SessionLocal() as s, pytest.raises(writers.Refused):
        writers_fleet.fleet_issue(s, _ins("fleet_issue"), _case(RELEASE), {})
    assert fake.patches == []


def test_tf_10_a_route_without_a_renewal_has_nothing_to_write(fake):
    with SessionLocal() as s, pytest.raises(writers.NotApplicable):
        writers_fleet.fleet_issue(s, _ins("fleet_issue"), _case({"id": "release", "dest": None}), {})
    assert fake.patches == []


def test_tf_10_harvest_issues_parts(fake):
    with SessionLocal() as s:
        sent = writers_fleet.parts_issue(s, _ins("parts_issue"), _case(HARVEST), {})
    assert [p for p, _ in fake.patches] == [f"{PARTS}/repair-orders/open/RO-1", f"{PARTS}/repair-orders/open/RO-2"]
    assert [b["issuedPart"] for _, b in fake.patches] == ["Motor armature", "Gearbox"]
    assert all(
        b["status"] == "part_issued" and b["issuedFrom"] == SERIAL and b["issuedKey"] == "APR-1.3.parts_issue"
        for _, b in fake.patches
    )
    assert sent.detail["orders"] == ["RO-1", "RO-2"]
    with SessionLocal() as s:
        writers_fleet.parts_issue(s, _ins("parts_issue"), _case(HARVEST), {})
    assert len(fake.patches) == 2  # a resend writes nothing more


# ------------------------------------------------------------------ the outcome
def _check(actual: float, predicted: float) -> int | None:
    with SessionLocal() as s:
        item = variance.check(s, _case(RELEASE), actual, predicted)
        s.commit()
        return item


def _items() -> list[tuple]:
    with SessionLocal() as s:
        q = "SELECT owner_role, title, type FROM work_item WHERE case_id = 'RT-TF10' AND status = 'open'"
        return [tuple(r) for r in s.execute(text(q)).all()]


def test_tf_10_variance_above_tolerance_opens_task():
    assert _check(850.0, 1000.0) is not None  # 15% below: over the 10%
    assert _items() == [("Finance", "Check the variance on RT-TF10", "variance_check")]
    assert _check(850.0, 1000.0) is None and len(_items()) == 1  # a second confirmation opens no second task


def test_tf_10_within_tolerance_no_task():
    assert _check(950.0, 1000.0) is None  # 5% below
    assert _check(160.0, 200.0) is None  # $40 below a small net: the $50 floor is the tolerance
    assert _items() == []
    assert _check(140.0, 200.0) is not None  # $60 below: over the floor
    assert variance.tolerance(1000.0) == 100.0 and variance.tolerance(200.0) == 50.0


def test_tf_10_agents_never_confirm_or_resend_for_a_person():
    assert forbidden("outcome.confirm")
