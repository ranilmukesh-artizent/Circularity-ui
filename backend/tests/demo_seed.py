"""The demo's seed beyond the industrial book (UI audit 26 Nov 2026, gaps 5 and 6): what a person sees at rest.

`seed()` runs after `starting.reset()` (scripts/reset_starting.py calls it; the tests that want the bare starting state never
do). Synthetic data only. Every case is opened through `case.open` (or the device lab's hook, which calls the same
`intake.open_case`), decided by `decide_case`, approved by a person's call and acknowledged by the system; agent runs go
through `runtime.start` and `run_until_blocked`, so their steps, holds and proposals are the runtime's own. Nothing here
approves for an agent or writes a case, run or proposal row directly.

Per non-industrial pack (tool_fleet, device, used_cars, telecom_network, medical_rental): one case held (a gate holds it
at stage `none`), one waiting for a person (`awaiting_approval`) and one closed. Agents: three runs of the `recover-chain`
agent on cases of three packs; each stops at a proposal held for a person with its reasons (value limit, confidence, taint).
The industrial book (128 cases, RT-1048) is never touched.
"""

import copy
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from di.connectors import extra
from di.connectors.adapters import device_lab as lab
from di.core.db import SessionLocal
from di.repositories import device_tradeins
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.agents import runtime
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.cases import store
from di.services.device import intake as device_intake
from tests import ucfixtures as uc
from tests.device_registry import seed_registry
from tests.helpers import call, tool_case_facts
from tests.test_device_intake import _doc as _device_doc
from tests.test_device_intake import _price as _device_price
from tests.test_medical_rental_paths import SCENARIOS as MR_SCENARIOS
from tests.test_medical_rental_paths import _open as _mr_open
from tests.test_tn_facts import _market as _tn_market
from tests.test_tn_facts import _open as _tn_open
from tests.test_tn_facts import _unit as _tn_unit
from tests.test_tn_facts import _write as _tn_write
from tests.test_tn_intake import _evidence as _tn_evidence
from tests.test_tn_intake import _job as _tn_job

ORG = "Customer A"
PACKS = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs"
EXTRA_SOURCES = {
    "used_cars": uc.SOURCES,
    "telecom_network": ("tn_inv", "tn_decom", "tn_bench", "tn_spares", "tn_broker"),
    "medical_rental": ("mr_rental", "mr_decon", "mr_biomed", "mr_assets"),
}
AGENT = "recover-chain"


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _get(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None, cid
    return c


def _publish(pack: str) -> None:
    """The shipped pack imported, submitted and approved as the org's (a person's calls), and its extra sources registered."""
    doc = copy.deepcopy(json.loads((PACKS / f"{pack}.json").read_text(encoding="utf-8")))
    doc["version"] = "1.9.3"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in EXTRA_SOURCES.get(pack, ()):
            extra.register(s, sid, ORG)
        s.commit()


def _approve_and_close(cid: str) -> None:
    """A person submits and approves the recommendation (a second person, the maker-checker pair); the system acknowledges
    each step of the plan, as the executing system's events do. The last acknowledgement closes the case."""
    c = _get(cid)
    if not c.get("submitted"):
        _ok(call("decision.submit", {"case_id": cid}, "admin"))
    body = {"case_id": cid, "reviewed": True, "rationale": "Reviewed against the evidence and the route's net."}
    _ok(call("decision.approve", body, "approver"))
    for _ in range(12):
        if _get(cid)["stage"] == "closed":
            return
        with SessionLocal() as s:
            r = invoke("adapter.acknowledge", {"case_id": cid, "simulated": True}, CallContext(actor=SYSTEM, session=s))
            if not r["ok"]:
                s.rollback()
                break
            s.commit()
    assert _get(cid)["stage"] == "closed", (cid, _get(cid)["stage"])


def _tool_fleet() -> dict[str, str]:
    base = {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 62}
    ids: dict[str, str] = {}

    def open_(asset: str, line: bool) -> str:
        facts = tool_case_facts(asset, base) if line else dict(base)
        body = {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": asset, "reason": "contract_end", "facts": facts}
        return str(_ok(call("case.open", body, "planner-a"))["case_id"])

    ids["held"] = open_("DEMO-CMH-0001", line=False)  # no active contract line: GR-07 holds every route
    ids["waiting"] = open_("DEMO-CMH-0002", line=True)
    ids["closed"] = open_("DEMO-CMH-0003", line=True)
    _approve_and_close(ids["closed"])
    return ids


def _device() -> dict[str, str]:
    _device_price("B", 330)
    docs = {k: _device_doc(n) for k, n in (("held", 701), ("waiting", 702), ("closed", 703))}
    with SessionLocal() as s:
        for d in docs.values():
            lab.land_tradein(s, d, ORG)
        s.commit()
    for k in ("waiting", "closed"):  # the held one has no registry check on file (P9-6.6)
        seed_registry(docs[k]["imei"])
    with SessionLocal() as s:
        device_intake.open_pending(s, ORG)
        s.commit()
        ids = {k: str(device_tradeins.by_imei(s, d["imei"]).case_id) for k, d in docs.items()}
    _approve_and_close(ids["closed"])
    return ids


def _used_cars() -> dict[str, str]:
    ids = {
        "held": uc.open_car(3)["id"],  # a lien on the title holds every route until it is released
        "waiting": uc.open_car(1)["id"],
        "closed": uc.open_car(10, like=1)["id"],
    }
    _approve_and_close(ids["closed"])
    return ids


def _telecom() -> dict[str, str]:
    ids: dict[str, str] = {}
    _tn_market()
    for k, n in (("waiting", 1), ("closed", 2)):
        ids[k] = _tn_open(_tn_unit(n))["id"]
    # on the tracker and the bench, not in the inventory: the match gate holds it
    (job,) = _tn_job("RJ-09", "SITE-301", [(3, "RAD-7700")])
    _tn_write("tn_decom", "removal_jobs", job)
    _tn_evidence(3)
    ids["held"] = _tn_open(job)["id"]
    _approve_and_close(ids["closed"])
    return ids


def _medical() -> dict[str, str]:
    ids = {
        "held": _mr_open(3, **MR_SCENARIOS["MR-S3"])["id"],  # no decontamination record: every route fails
        "waiting": _mr_open(1, **MR_SCENARIOS["MR-S1"])["id"],
        "closed": _mr_open(2, **MR_SCENARIOS["MR-S1"])["id"],
    }
    _approve_and_close(ids["closed"])
    return ids


def _run(case_id: str, account: str = "planner-a", tainted: bool = False) -> str:
    """One run of the chain agent on the case, driven as the worker's job does until it waits for a person."""
    with SessionLocal() as s:
        run_id = runtime.start(s, AGENT, "stage_chain", case_id, account=account)
        if tainted:  # the run read untrusted content: every write of it is held (P9-2.4)
            s.execute(
                text("UPDATE agent_run SET state = state || CAST(:t AS jsonb) WHERE id = :i"),
                {"t": json.dumps({"tainted": True}), "i": run_id},
            )
        s.commit()
    with SessionLocal() as s:
        runtime.run_until_blocked(s, run_id)
        s.commit()
    return run_id


def _agents(cases: dict[str, dict[str, str]]) -> list[str]:
    """Three runs: a used car over the recon approval limit (value), a car whose inspection is only an estimate (confidence)
    and a telecom unit whose run read untrusted content (taint). Each stops at a held proposal for a person."""
    over = uc.open_car(7)["id"]  # recon over AP-UC-RECON
    uc.write_car(9, like=1)
    uc.write("uc_insp", "inspections", uc.records(9, 1)["uc_insp"][1] | {
        "status": "scheduled", "conditionScore": None, "odometerPhotoReading": None, "reconEstimate": None,
        "reconLines": [], "completedAt": None})  # fmt: skip
    body = {"org_unit_id": ORG, "template_key": "used_cars", "asset_key": uc.vin_key(ORG, uc.vin(9)), "reason": "lease_end",
            "facts": {"vin": uc.vin(9), "mileage": 38000, "return_date": "2026-10-03"}}  # fmt: skip
    estimate = str(_ok(call("case.open", body, "planner-a"))["case_id"])
    return [_run(over), _run(estimate), _run(cases["telecom_network"]["waiting"], tainted=True)]


def seed() -> dict[str, Any]:
    """Seed the cases of every non-industrial pack, then the agent runs. Returns the ids: {"cases": {pack: {held, waiting,
    closed}}, "runs": [...]}."""
    # THE no-model switch of the seed (R16: code answers when no model does): a loop that never finds a model, set for the
    # whole seed and restored after. Every model path of the seed (stage reads, agent loops) goes through `runtime.loop_runner`
    # / `_stage_loop`, so a key in the environment (GROQ_API_KEY) cannot make a reset call a model.
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))
    try:
        for pack in ("used_cars", "telecom_network", "medical_rental"):
            _publish(pack)
        cases = {
            "tool_fleet": _tool_fleet(),
            "device": _device(),
            "used_cars": _used_cars(),
            "telecom_network": _telecom(),
            "medical_rental": _medical(),
        }
        runs = _agents(cases)
    finally:
        runtime.set_loop(None)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()
    return {"cases": cases, "runs": runs}
