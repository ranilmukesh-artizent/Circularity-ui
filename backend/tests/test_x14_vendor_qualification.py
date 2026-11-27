"""Plan 9, P9-13.3 (story X-14): a downstream vendor qualifies on its certificate and the date it is judged at.

`qualify` (pure) judges the case org's canonical vendors for a route's `downstream_roles`; G-DS-1 blocks a route no vendor
qualifies for and says why with the date; the decision records the chosen vendor as `vendor_check` (the certificate reference
kept); a decision as of an earlier date judges on that date. Legal note: certificate standards are research summaries;
Kinective's Legal team reviews them before reliance.
"""

import json
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.cases import decide as decide_mod
from di.services.cases.vendor_facts import records
from di.services.modeler.gate_checks.downstream import check_downstream_vendor
from di.services.modeler.gates import pack_gates
from di.services.modeler.pack import Pack, load_pack
from di.services.modeler.vendor_qualification import chosen, qualify
from tests.test_tn_routing import decide, route, sample

PACK = load_pack("telecom_network")
VND_U = {"id": "VND-U", "name": "Uncertified vendor", "role": "recycler", "cert_ref": "ISO14001-VU", "cert_standard": "ISO 14001",
         "cert_status": "LAPSED", "cert_valid_to": "2026-08-12"}  # fmt: skip
VND_B = {"id": "VND-B", "name": "Approved vendor B", "role": "recycler", "cert_ref": "R2V3-VB", "cert_standard": "R2v3",
         "cert_status": "approved", "cert_valid_to": "2027-06-30"}  # fmt: skip
RECYCLE = {"id": "recycle", "downstream_roles": ["recycler"]}
AFTER = date(2026, 11, 26)  # the pinned clock's day: after VND-U's certificate ran out
BEFORE = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


def _redeploy_pack():
    """The telecom pack with redeploy (TN-S1's recommendation) handed to a recycler: the unit's route is gated by G-DS-1."""
    doc = json.loads(PACK.model_dump_json())
    next(r for r in doc["routes"] if r["id"] == "redeploy")["downstream_roles"] = ["recycler"]
    next(g for g in doc["gates"] if g["id"] == "G-DS-1")["params"]["routes"] = ["redeploy"]
    return Pack.model_validate(doc)


def _gate():
    return next(g for g in pack_gates(PACK) if g.id == "G-DS-1")


def test_x_14_expired_certificate_excludes_with_date():
    [c] = qualify([VND_U], RECYCLE, AFTER)
    assert not c.qualified and "expired on 12 Aug 2026" in c.reason
    assert c.reason == "Uncertified vendor's ISO 14001 certificate ISO14001-VU expired on 12 Aug 2026."
    [n] = qualify([{"id": "V-N", "name": "Nova", "role": "recycler"}], RECYCLE, AFTER)
    assert not n.qualified and n.reason == "Nova has no certificate on file."


def test_x_14_valid_certificate_ref_kept():
    [c] = qualify([VND_B], RECYCLE, AFTER)
    assert c.qualified and c.cert_ref == "R2V3-VB" and c.valid_to == date(2027, 6, 30)
    r = check_downstream_vendor({"vendors": [VND_U, VND_B], "gateNow": "2026-11-26T09:00:00+00:00"}, PACK, _gate())
    assert r is not None and r.passed and r.reason == "Approved vendor B · R2v3 R2V3-VB valid to 30 Jun 2027"
    d = decide(sample("TN-S1") | {"vendors": [VND_U, VND_B]}, pack=_redeploy_pack())
    assert d.vendor_check is not None and d.vendor_check["cert_ref"] == "R2V3-VB" and d.vendor_check["route"] == "redeploy"
    c2 = {"id": "X"}
    decide_mod.write_back(c2, d)
    assert c2["vendorCheck"]["cert_ref"] == "R2V3-VB"  # the case keeps it; the approval's journal row names it


def test_x_14_no_qualified_vendor_blocks_route():
    d = decide(sample("TN-S1") | {"vendors": [VND_U]}, pack=_redeploy_pack())
    r = route(d, "redeploy")
    assert r["excluded"] and "expired on 12 Aug 2026" in r["failReason"]
    assert d.route != "redeploy" and d.vendor_check is None  # the recommendation moves to the next eligible route
    gate = next(g for g in d.gates if g.gate_id == "G-DS-1")
    assert not gate.passed and gate.effect.routes == ("redeploy",)


def test_x_14_as_of_date_used():
    from di.services.cases.decide import decide_case
    from di.services.modeler.compile import FlowVersion
    from tests.test_tn_routing import nest

    d = decide_case(nest(sample("TN-S1") | {"vendors": [VND_U]}), _redeploy_pack(), FlowVersion(None, 3, ()), BEFORE, queue=[])
    assert not route(d, "redeploy")["excluded"] and d.vendor_check is not None and d.vendor_check["vendor_id"] == "VND-U"


def test_x_14_best_qualified_vendor_has_the_best_rate():
    cheap, dear = VND_B | {"id": "V1", "rate": 1.0}, VND_B | {"id": "V2", "rate": 2.5, "cert_ref": "R2V3-V2"}
    assert chosen([cheap, dear, VND_U], RECYCLE, AFTER)["cert_ref"] == "R2V3-V2"
    assert chosen([VND_U], RECYCLE, AFTER) is None


def test_x_14_no_vendor_records_leaves_the_decision_alone():
    plain = decide(sample("TN-S1"), pack=_redeploy_pack())
    assert plain.vendor_check is None and plain.route == "redeploy"


def test_x_14_vendors_read_from_the_canonical_store():
    with SessionLocal() as s:
        for v in (VND_U, VND_B):
            s.execute(text("DELETE FROM canonical WHERE model = 'vendor' AND key = :k"), {"k": "X14-" + v["id"]})
            s.execute(
                text("INSERT INTO canonical (model, key, data) VALUES ('vendor', :k, CAST(:d AS jsonb))"),
                {"k": "X14-" + v["id"], "d": __import__("json").dumps({k: x for k, x in v.items() if k != "id"})},
            )
        s.commit()
        try:
            got = {v["id"]: v for v in records(s)}
            assert got["X14-VND-B"]["cert_ref"] == "R2V3-VB" and got["X14-VND-U"]["cert_status"] == "LAPSED"
        finally:
            s.execute(text("DELETE FROM canonical WHERE model = 'vendor' AND key LIKE 'X14-%'"))
            s.commit()


@pytest.mark.parametrize("key", ["tool_fleet", "used_cars", "telecom_network", "medical_rental"])
def test_x_14_packs_name_their_downstream_roles(key):
    pack = load_pack(key)
    roles = {r.id: r.downstream_roles for r in pack.routes if r.downstream_roles}
    assert roles and all(r for r in roles.values())


def test_p9_13_14_f3_replay_judges_vendors_as_intake(monkeypatch):
    """Review 13 F3 (Review Focus 3): the replay reads the canonical vendors as intake does. The only recycler's certificate
    ran out before the history's dates, so redeploy (handed to a recycler here) is excluded by intake and by the replay alike."""
    from di.services.cases import vendor_facts
    from di.services.cases.decide import decide_case
    from di.services.modeler.compile import FlowVersion
    from di.services.modeler.replay_samples import telecom_network as G
    from di.services.replay import run as replay_run
    from di.services.replay import telecom as T

    monkeypatch.setattr(vendor_facts, "records", lambda s: [VND_U])  # the canonical store holds only the expired recycler
    pack, fv = _redeploy_pack(), FlowVersion(None, 3, ())
    items = T.items(G.rows()[:63], pack)
    blind = T.replay(items, fv, pack=pack).decided  # no session: what the replay decided before the fix
    redeployed = [it for it in items if blind[str(it["item_id"])][0] == "redeploy"]
    assert redeployed, "the sample day has units the flow redeploys when vendors are not judged"
    with SessionLocal() as s:
        replayed = T.replay(items, fv, pack=pack, session=s).decided
        for it in redeployed[:5]:
            facts, _ = replay_run.as_of_facts(it)
            case = T.telecom_case(replay_run.case_input(it, facts, pack))
            intake = decide_case(case, pack, fv, it["decided_at"], session=s, queue=[])
            assert intake.route != "redeploy"
            assert replayed[str(it["item_id"])] == (intake.route, intake.net), it["item_id"]


def test_x_14_industrial_unchanged():
    assert all(not r.downstream_roles for r in load_pack("industrial").routes)
    assert "G-DS-1" not in {g.id for g in pack_gates(load_pack("industrial"))}
