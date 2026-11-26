"""Plan 9, P9-4.8 (story SD-07): a batch is decided per tool and shown as one split.

`decide_batch` decides each line alone with `decide_ticket`, then lets the swaps take refurbished units in line order until the
stock of the class runs out (a line that loses the unit takes its next option). The batch case's routes are `split` (the sum of
the lines' chosen options, the recommendation) and, to compare, `all_fix` and `all_upgrade`. A hold on any line (GR-14, GR-C1,
GR-S1, GR-S3) holds the whole batch, with the line named. The batch is approved, like any case, by a person through
`decide_case`'s holds (I-6, I-10, I-11): this task adds no action, so nothing joins FORBIDDEN_ACTIONS.

No model step (R16): the split, the figures and every reason are computed, so there are no model tests. The valuer's cases are
pure (crafted inputs, stock 30 as the spec says); the case page and the three paths run on tickets written to the table.
The seeded `CS0010050` of the source-sim mock is checked by the lead on the main stack (the 9/11/2 split there is the mock's).

It starts and ends with the demo reset.
"""

import json
from decimal import Decimal

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.repositories import service_tickets
from di.services.agents.forbidden import forbidden
from di.services.cases import decide, intake, store
from di.services.modeler.valuers import service_desk as sdv
from di.services.service_desk import intake as sd
from tests.helpers import call, client, h, tool_case_facts
from tests.test_service_desk_options import ORG, _history, _line, _stock, fresh  # noqa: F401 - `fresh` is the module's fixture
from tests.test_valuer_service_desk import _inputs
from tests.test_valuer_service_desk import _line as _vline

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
LAST_LINE_STOCK = "Refurbished stock used by earlier lines of this batch"


def _batch_lines() -> list[dict]:
    """22 lines: 9 old tools (an upgrade is worth more), 11 young and uncovered (only a fix), 2 covered (a swap is cheapest)."""
    old = [_vline(n, life=90, pct=0.25, cap=300, stock=30) for n in range(1, 10)]
    young = [_vline(n, life=40, stock=30) for n in range(10, 21)]
    swaps = [_vline(n, life=40, covered=True, swap=True, stock=30) for n in range(21, 23)]
    return [*old, *young, *swaps]


def test_sd_07_batch_split_9_11_2():
    inputs = _inputs(*_batch_lines())
    b = sdv.decide_batch(inputs)
    assert b.split == {"upgrade": 9, "fix": 11, "swap": 2}
    assert len(b.lines) == 22
    for ln, own in zip(b.lines, inputs["lines"], strict=True):  # each line is what decide_ticket says of that line alone
        assert ln["best"] == sdv.decide_ticket(_inputs(own))["lines"][0]["best"]
    chosen = [next(o for o in ln["options"] if o["k"] == ln["best"]) for ln in b.lines]
    assert b.totals["margin"] == sum((Decimal(str(o["margin"])) for o in chosen), Decimal(0))
    assert b.totals["customer_price"] == sum((Decimal(str(o["customer_price"])) for o in chosen), Decimal(0))
    assert all(isinstance(v, Decimal) for v in b.totals.values())


def test_sd_07_the_batch_case_options_are_split_and_the_comparisons():
    t = sdv.batch_ticket(_inputs(*_batch_lines()))
    assert [o["k"] for o in t["options"]] == ["split", "all_fix", "all_upgrade"] and t["best"] == "split"
    split, all_fix, all_up = t["options"]
    assert split["eligible"] and split["why"] == "Upgrade 9 · Fix 11 · Covered swap 2"
    assert all_fix["eligible"] and not all_up["eligible"]  # the 11 young tools are not offered an upgrade (BR-S1)
    assert split["expected_margin"] >= all_fix["expected_margin"]
    assert t["batch"]["split"] == {"upgrade": 9, "fix": 11, "swap": 2}


def test_sd_07_stock_runs_out_in_line_order():
    two = [_vline(1, life=40, covered=True, swap=True, stock=1), _vline(2, life=40, covered=True, swap=True, stock=1)]
    b = sdv.decide_batch(_inputs(*two))
    assert b.lines[0]["best"] == "swap"
    second = {o["k"]: o for o in b.lines[1]["options"]}
    assert second["swap"]["eligible"] is False and second["swap"]["why"] == LAST_LINE_STOCK
    assert b.lines[1]["best"] == "fix" and b.split == {"upgrade": 0, "fix": 1, "swap": 1}
    plenty = sdv.decide_batch(_inputs(*[{**x, "refurb_stock": 2} for x in two]))
    assert plenty.split["swap"] == 2  # the stock covers both


def test_sd_07_a_line_that_holds_holds_the_batch_with_the_line_named():
    big = _vline(2, point=700, life=40, covered=True, stock=30)  # a fix over $600 (GR-14); no swap allowed
    t = sdv.batch_ticket(_inputs(_vline(1, life=40, stock=30), big))
    holds = sdv.approval_holds(t, "split")
    assert [x["id"] for x in holds] == ["GR-14"] and "S-2" in holds[0]["reason"] and holds[0]["owner"] == "Fleet manager"
    assert sdv.approval_holds(t, "all_fix")[0]["id"] == "GR-14"
    ok = sdv.batch_ticket(_inputs(_vline(1, life=40, stock=30), _vline(2, life=40, stock=30)))
    assert sdv.approval_holds(ok, "split") == []


# ------------------------------------------------------------------ the case: one case, one split, one page
def _batch_ticket(number: str, lines: list[dict]) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO service_ticket (number, org_unit_id, account, market, site, batch_id, lines, requester_role, "
                "loaner_promised, opened_at, source) VALUES (:n, :o, 'ACC-US-0042', 'US', 'Denver', 'BATCH-0050', "
                "CAST(:l AS jsonb), 'Site manager', false, '2026-10-07T09:00:00+00:00', 'sdesk')"
            ),
            {"n": number, "o": ORG, "l": json.dumps(lines)},
        )
    for x in lines:
        tool_case_facts(x["serial"], {"cls": x["model_class"]})


def _open_batch() -> dict:
    _history()
    _stock(1)  # one refurbished unit: the first covered tool swaps, the second takes its next option
    lines = [
        _line("CRH-46001", age=18),  # fleet cover, 50% of life: swap, fix or upgrade
        _line("CRH-46002", age=18),
        _line("CRH-46003", age=10, cover="none"),  # no cover, young: a fix only
        _line("CRH-46004", age=33, cover="none"),  # old, no cover: an upgrade may be worth more
    ]
    _batch_ticket("CS0010050", lines)
    with SessionLocal() as s:
        row = next(t for t in service_tickets.pending(s, ORG) if t.number == "CS0010050")
        c = sd.open_from_ticket(s, row, "system")
        s.commit()
    with SessionLocal() as s:
        return store.get(s, c["id"])


def test_sd_07_the_batch_case_is_one_split_recommended_and_the_page_shows_it():
    c = _open_batch()
    assert [r["id"] for r in c["routes"]] == ["split", "all_fix", "all_upgrade"] and c["recommendation"]["id"] == "split"
    d = c["serviceDesk"]
    sp = d["split"]
    assert sum(sp["counts"].values()) == 4 and sp["counts"]["swap"] <= 1  # one unit in stock
    assert [x["k"] for x in sp["lines"]] == [ln["best"] for ln in d["lines"]]
    for ln in d["lines"]:  # a line's option is what decide_ticket says of it, given the stock the earlier lines left
        assert ln["best"] in {o["k"] for o in ln["options"] if o["eligible"]}
    r = client.get(f"/api/screens/case/{c['id']}", headers=h("admin"))
    assert r.status_code == 200, r.text
    v = r.json()["case"]["serviceDesk"]
    assert v["split"]["counts"] == sp["counts"] and v["split"]["totals"]["margin"] == pytest.approx(sp["totals"]["margin"])
    assert v["approval"]["route"] == "split"


def test_sd_07_paths_agree_for_a_batch_intake_reevaluate_and_decide_case():
    """R19: opening the case, `case.reevaluate` and the decider on the stored case give the same split and the same margin."""
    c = _open_batch()
    seen = {"intake": (c["serviceDesk"]["split"]["counts"], c["serviceDesk"]["split"]["totals"]["margin"])}
    for action, body, who in (
        ("decision.submit", {}, "admin"),
        ("decision.decline", {"reason": "Check again."}, "approver"),  # a person declines: the case waits for re-evaluation
        ("case.reevaluate", {}, "admin"),
    ):
        r = call(action, {"case_id": c["id"], **body}, who)
        assert r["ok"], r
    with SessionLocal() as s:
        again = store.get(s, c["id"])
        seen["reevaluated"] = (again["serviceDesk"]["split"]["counts"], again["serviceDesk"]["split"]["totals"]["margin"])
        fv = intake.flow_version(s, again)
        pack = intake._pack(s, again)
        dec = decide.decide_case(again, pack, fv, session=s)
        assert dec.ticket is not None
        seen["decided"] = (dec.ticket["batch"]["split"], dec.ticket["batch"]["totals"]["margin"])
    assert seen["intake"] == seen["reevaluated"] == seen["decided"]


def test_sd_07_agents_never_approve_a_batch():
    assert forbidden("decision.approve") and forbidden("decision.override") and forbidden("decision.decline")
