"""Plan 9, P9-6.13 (story DV-08): ageing suggestions from live listings, accepted into rules through maker-checker.

A listing that sits on Offers with no offer, or on Buy Now unsold, past the customer's days is suggested a move to the next
channel: Offers to Auction after `offers_to_auction_days` (14, or 7/10/21), Buy Now to Offers after `buynow_to_offers_days`
(21). `device.ageingSuggestions` (read, nothing saved) places each as a checked, simulated rule proposal; accepting is the
person's own `flow.saveDraft`, then a different person approves and publishes it. Every number is counted and summed from the
listing rows (no language model). The tests seed their own listings (ids `AGE-T-*`) and clear the table.
"""

import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from di.core import clock
from di.core.db import SessionLocal, engine
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.agents.forbidden import forbidden
from di.services.cases import store
from di.services.device import ageing
from tests import flowkit, starting
from tests.helpers import call

ORG = "Customer A"
RULE = {"action": "require", "path": "auction", "scope": {"listChannel": ["offers"], "listDaysMin": 14, "offersMax": 0}}


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM device_listing"))
        conn.execute(text("DELETE FROM provenance WHERE source_id IN ('dvlab', 'dvreg') AND key LIKE 'IMEI:%'"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('condition', 'asset') AND key LIKE 'IMEI:%'"))
        for t in ("device_tradein", "device_price_point"):
            conn.execute(text(f"DELETE FROM {t}"))  # noqa: S608 - fixed names


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    flowkit.reset_flows()
    _FORKED.clear()
    yield
    starting.reset()
    _clean()
    flowkit.reset_flows()


def _list(n: int, channel: str, days: int, offers: int = 0, price: float = 100.0, org: str = ORG, case_id: str | None = None,
          imei: str | None = None, tag: str = "A") -> list[str]:  # fmt: skip
    """`n` live listings on `channel` listed `days` ago with `offers` offers."""
    ids = []
    with engine.begin() as conn:
        for k in range(n):
            lid = f"AGE-T-{tag}-{channel[:2]}-{days}-{k}"
            ids.append(lid)
            conn.execute(
                text(
                    "INSERT INTO device_listing (listing_id, org_unit_id, imei, case_id, channel, price, listed_at, offers, "
                    "status, updated_at) VALUES (:i, :o, :m, :c, :ch, :p, :at, :n, 'live', now())"
                ),
                {"i": lid, "o": org, "m": imei or f"3599900{tag}{days:02d}{k:05d}"[:15], "c": case_id, "ch": channel, "p": price,
                 "at": clock.now() - timedelta(days=days), "n": offers},
            )  # fmt: skip
    return ids


def _seed() -> None:
    """12 Offers listings past 14 days with no offer (6 past 21), 9 Buy Now past 21 days, and some that must not count."""
    _list(6, "Offers", 15, price=160)
    _list(6, "Offers", 22, price=160)
    _list(9, "Buy Now", 25, price=200)
    _list(3, "Offers", 5)  # too young
    _list(3, "Offers", 30, offers=2, tag="B")  # has an offer
    _list(3, "Auction", 40)  # already on Auction
    _list(3, "Buy Now", 10, tag="B")  # too young


_FORKED: dict[str, int] = {}


def _fid() -> int:
    """The device flow of Customer A, which planner.a forks from the workspace's (a planner sees only their own tenant)."""
    if ORG not in _FORKED:
        _FORKED[ORG] = flowkit.ok(call("flow.fork", {"template_key": "device", "org_unit_id": ORG}, "planner-a"))["flow_id"]
    return _FORKED[ORG]


def _out(i: dict, user: str = "planner-a") -> dict:
    return flowkit.ok(call("device.ageingSuggestions", {"flow_id": _fid()} | i, user))


def test_dv_08_offers_to_auction_after_14_days():
    _seed()
    out = _out({})
    s = next(x for x in out["suggestions"] if x["to"] == "auction")
    assert s["text"] == "Move 12 Offers listings to Auction: 14 days, no offer"
    assert s["n"] == 12 and len(s["listings"]) == 12 and s["value"] == 12 * 160
    assert s["rule"] == RULE and s["proposal"]["kind"] == "rule" and s["proposal"]["guard"] is None
    again = _out({"offers_days": 21})
    s21 = next(x for x in again["suggestions"] if x["to"] == "auction")
    assert s21["n"] == 6 and s21["text"] == "Move 6 Offers listings to Auction: 21 days, no offer"
    assert s21["rule"]["scope"]["listDaysMin"] == 21
    f, _ = flowkit.get(_fid())
    assert f.draft is None  # a suggestion is never applied by itself


def test_dv_08_buynow_to_offers_after_21_days():
    _seed()
    out = _out({})
    (s,) = [x for x in out["suggestions"] if x["to"] == "offers"]
    assert s["text"] == "Move 9 Buy Now listings to Offers: 21 days unsold" and s["n"] == 9 and s["value"] == 9 * 200
    assert s["rule"] == {"action": "require", "path": "offers", "scope": {"listChannel": ["buynow"], "listDaysMin": 21}}


def test_dv_08_oldest_band_first():
    _seed()
    got = [(x["to"], x["days"]) for x in _out({})["suggestions"]]
    assert got == [("offers", 21), ("auction", 14)]  # the 21-day band first, then the 14-day one
    with SessionLocal() as s:
        rows = ageing.live_of_org(s, "workspace", clock.now().date())
    cfg = ageing.Settings(offers_to_auction_days=21, buynow_to_offers_days=21)
    equal = ageing.suggest(rows, cfg, clock.now().date())
    assert [x.to for x in equal] == ["offers", "auction"]  # the same 21 days: Buy Now's $1,800 before Offers' $960
    assert equal[0].value > equal[1].value


def test_dv_08_only_the_flows_org_and_tenant_listings():
    _list(2, "Offers", 20, org="Customer B", tag="C")
    _list(4, "Offers", 20, org=ORG, tag="D")
    (s,) = _out({})["suggestions"]
    assert s["n"] == 4  # the flow of Customer A: its own listings only
    ws = flowkit.flow_id("device", "workspace")
    both = flowkit.ok(call("device.ageingSuggestions", {"flow_id": ws}, "admin"))["suggestions"]
    assert [x["n"] for x in both] == [6]  # the workspace flow, read by an admin: every org's
    refused = call("device.ageingSuggestions", {"flow_id": ws}, "planner-a")
    assert refused["ok"] is False and refused["error"]["code"] == "tenant_boundary"


def test_dv_08_accept_becomes_rule_via_maker_checker():
    from tests.test_device_settle import IMEI, _open

    cid = _open()["id"]
    _list(1, "Offers", 15, price=300, case_id=cid, imei=IMEI, tag="E")  # the case's own listing: 15 days, no offer
    fid = _fid()
    out = flowkit.ok(call("device.ageingSuggestions", {"flow_id": fid}, "planner-a"))
    s = next(x for x in out["suggestions"] if x["to"] == "auction")
    graph = s["proposal"]["graph"]
    flowkit.ok(call("flow.saveDraft", {"flow_id": fid, "graph": graph}, "planner-a"))  # accepting is the person's own draft
    flowkit.ok(call("flow.submit", {"flow_id": fid}, "planner-a"))
    refused = call("flow.approve", {"flow_id": fid}, "planner-a")
    assert refused["ok"] is False  # the maker never approves their own change
    flowkit.ok(call("flow.approve", {"flow_id": fid}, "approver"))
    flowkit.ok(call("flow.publish", {"flow_id": fid}, "approver"))
    # a person declines the open case so that it waits for re-evaluation, then it is valued again under the published rule
    assert call("decision.submit", {"case_id": cid}, "admin")["ok"]
    assert call("decision.decline", {"case_id": cid, "reason": "Re-check the channel."}, "approver")["ok"]
    assert call("case.reevaluate", {"case_id": cid}, "planner-a")["ok"]
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c["recommendation"]["id"] == "auction"
    assert next(n["rid"] for n in graph["nodes"] if n["t"] == "rule" and n.get("ai")) in c["rulesApplied"]
    assert c["valuer"]["inputs"]["listing"]["channel"] == "offers" and c["valuer"]["inputs"]["listing"]["days"] == 15


def test_dv_08_a_rule_on_offers_leaves_other_cases_alone():
    """The valuer reads the case's listing: a lot with none, or one on Buy Now, is out of the rule's scope."""
    from di.services.modeler.valuers import device

    lot = dict(device.sample_lots()[0])
    assert not device.in_scope(lot, RULE["scope"])  # a lot with no listing
    lot["inputs"] = {"listing": {"channel": "buynow", "days": 40, "offers": 0, "offers_under": -1}}
    assert not device.in_scope(lot, RULE["scope"])
    lot["inputs"] = {"listing": {"channel": "offers", "days": 14, "offers": 0, "offers_under": -1}}
    assert device.in_scope(lot, RULE["scope"])
    lot["inputs"]["listing"] |= {"offers": 1, "offers_under": 0}
    assert not device.in_scope(lot, RULE["scope"])


def test_dv_08_the_action_is_a_person_only_one():
    """R21: the suggestions are read by a person; no agent may run the action (or reach it through the tool catalogue)."""
    assert forbidden("device.ageingSuggestions")
    fid = _fid()
    r = call("device.ageingSuggestions", {"flow_id": fid}, "warehouse1")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    with SessionLocal() as s:
        agent = invoke("device.ageingSuggestions", {"flow_id": fid}, CallContext(actor=SYSTEM, session=s, preparer="gap"))
    assert agent["ok"] is False


def test_dv_08_rule_scope_reads_the_listing_not_other_cases():
    """The dims are part of the pack, with their wording (rule text reads back)."""
    from di.services.modeler.templates import load_template
    from di.services.modeler.text import rule_text

    t = load_template("device")
    assert {d.key: d.kind for d in t.dims if d.key in ("listChannel", "listDaysMin", "offersMax")} == {
        "listChannel": "set", "listDaysMin": "min", "offersMax": "max",
    }  # fmt: skip
    words = rule_text(t, RULE)
    assert "listed on Offers" in words and "14+ days listed" in words and "at most 0 offers" in words
    pack = json.loads((__import__("pathlib").Path(ageing.__file__).parents[1] / "modeler/packs/device.json").read_text("utf-8"))
    cfg = pack["valuer"]["params"]["ageing"]
    assert (cfg["offers_to_auction_days"], cfg["offers_choices"], cfg["buynow_to_offers_days"]) == (14, [7, 10, 14, 21], 21)


def test_dv_08_the_daily_job_values_a_waiting_listed_case_as_an_agent():
    """`device.ageing` wakes a listed case that waits for re-evaluation: the call is the agent's, judged by the hold policy."""
    from tests.test_device_settle import IMEI, _open

    cid = _open()["id"]
    _list(1, "Offers", 15, price=300, case_id=cid, imei=IMEI, tag="G")
    assert call("decision.submit", {"case_id": cid}, "admin")["ok"]
    assert call("decision.decline", {"case_id": cid, "reason": "Re-check the channel."}, "approver")["ok"]
    with SessionLocal() as s:
        done = ageing.reevaluate_listed(s, clock.now().date(), "coordinator")
        s.commit()
        assert list(done) == [cid]
        c = store.get(s, cid)
    assert done[cid] in ("done", "held")  # the hold policy judges an agent's write: it runs, or waits as a proposal for a person
    assert (done[cid] == "done") == (c["stage"] != "reeval")
    if done[cid] == "done":
        with SessionLocal() as s:
            assert ageing.reevaluate_listed(s, clock.now().date(), "coordinator") == {}  # nothing waits any more


def test_dv_08_f9_an_agent_on_a_persons_token_cannot_read_the_suggestions():
    """R21: the same planner reads them, but the call an agent prepared on that token is refused by the pipeline."""
    from tests.helpers import client, h

    fid = _fid()
    assert call("device.ageingSuggestions", {"flow_id": fid}, "planner-a")["ok"] is True
    for pre in ({"X-Circularity-Preparer": "gap"}, {"X-Circularity-Preparer": "gap", "X-Circularity-Confirmed": "true"}):
        r = client.post("/api/actions/device.ageingSuggestions", json={"flow_id": fid}, headers=h("planner-a") | pre).json()
        assert r["ok"] is False and r["error"]["code"] == "approval_required", r
