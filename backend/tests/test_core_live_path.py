"""P9-12.8 live path (story NS-CORE-03): a synced core reaches its case through intake, never injected.

The mock's cores (here the adapter's `map` run on them, as in tests/test_ns_core.py) are written to the canonical store as
source `core_ret` does; `case.open` for the core's asset key then reads them (di.services.cases.core_evidence, through
`gate_hold.attach_evidence`): the case's `core` and the X-15 evidence records. Core C-0004 (declared ALT-1450, a starter seen)
is held at intake for a person with `part_family_mismatch`; the release needs `approve.decisions` (Approver; a Planner only
with an approval limit). Synthetic data.
"""

from typing import Any

import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.canonical.schema import serial_key
from tests.helpers import call
from tests.test_ns_core import (  # noqa: F401 - `fresh` is a fixture
    CRACKED,
    FULL,
    MISMATCH,
    REPEAT,
    _case_now,
    _held_with,
    _intake,
    _ok,
    _prepared,
    fresh,
)

pytestmark = pytest.mark.usefixtures("no_synced_conflicts", "fresh")
ORG = "Customer A"


def _sync(core: dict[str, Any]) -> str:
    """What a sync of the core returns system does for one core: map it, apply the facts as source `core_ret`."""
    rec = Record("cores", core["coreId"], {**core, "org_unit_id": ORG}, "http://source-sim/core-returns/api/cores")
    with SessionLocal() as s:
        canonical.apply(s, "core_ret", ADAPTERS["core_ret"].map(rec))
        s.commit()
    return serial_key(ORG, core["coreId"])


def _open_synced(core: dict[str, Any]) -> str:
    key = _sync(core)
    body = {"org_unit_id": ORG, "template_key": "auto_core", "asset_key": key, "reason": "manual",
            "facts": {"family": "alternator", "deposit": 85}}  # fmt: skip
    return str(_ok(call("case.open", body, "planner-a"))["case_id"])


@pytest.fixture(autouse=True)
def _forget_cores():
    def forget() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": f"{ORG}:C-000%"})
            conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": f"{ORG}:C-000%"})

    forget()
    yield
    forget()


def test_ns_core_03_synced_family_mismatch_is_held_through_intake():
    cid = _open_synced(MISMATCH)
    core = _case_now(cid)["core"]
    assert core["checks"] == MISMATCH["checks"] and core["observedPartNumber"] == "STR-2210"
    f = _held_with(cid, "part_family_mismatch")
    assert f["signals"][0]["value"] == ["model"]


def test_ns_core_03_synced_repeat_returner_is_held_through_intake():
    cid = _open_synced(REPEAT)
    assert _case_now(cid)["core"]["dealerRejects"] == REPEAT["dealerRejects"]
    assert _held_with(cid, "repeat_returner")["signals"][0]["value"] == 3


def test_ns_core_01_synced_core_gets_its_credit_and_a_clean_one_is_not_held():
    ok, bad = _open_synced(FULL), _open_synced(CRACKED)
    assert _intake(ok).output["fraud"]["held"] is False and _case_now(ok).get("fraud") is None
    reman = next(r for r in _case_now(bad)["routes"] if r["id"] == "reman")
    assert reman["excluded"] and "no_cracks" in reman["failReason"]


def test_ns_core_03_the_release_role():
    cid = _open_synced(MISMATCH)
    _held_with(cid, "part_family_mismatch")
    why = "Checked the photos with the dealer; the part is the declared one."
    assert _prepared("fraud.release", {"case_id": cid, "reason": why})["ok"] is False  # an agent: never
    planner = call("fraud.release", {"case_id": cid, "reason": why}, "planner-a")
    assert planner["ok"] is False  # a Planner without an approval limit may not
    assert _ok(call("fraud.release", {"case_id": cid, "reason": why}, "approver"))["status"] == "released"
