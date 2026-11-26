"""Plan 9, P9-5.7 (story CR-07): a renewal's outcome is recorded on its refresh case and compared with what the
proposal predicted.

The fleet contract system moves a contract's `renewalStatus` to `renewed` or `lapsed`; after the sync
`di.services.refresh_outcome.record`
writes `renewalOutcome` on the contract's refresh case (renewed or not, fee before and after, the swaps of the sent proposal, and
what the proposal predicted). `di.repositories.renewals.outcomes` reads the ended contracts of the fleet's history and
those cases;
`screens.analytics.renewals` gives the renewal rate with and without a proposal, overall and per market and size band, the
prediction against what happened, and the caveat. All of it is counts, ratios and the contract's own figures (R16): no
model step, so
no `AgentLoop` and no model tests. Recording is the system's act from the source's fact; it adds no action
(`outcome.confirm` stays a
person's and is unchanged), so FORBIDDEN_ACTIONS does not move.
"""

from datetime import date

import pytest

from di.core.db import SessionLocal
from di.repositories import contract_history, renewals
from di.services import refresh_outcome
from di.services.canonical import store as canonical
from di.services.cases import store
from tests.helpers import client, h
from tests.test_cr_tool_action import ORG, refresh_case  # noqa: F401 - the fixture: FC-30140, two tools, US, one case

TODAY = date(2026, 10, 7)
CAVEAT = (
    "Contracts that got a proposal may differ from those that did not (for example larger or better accounts). "
    "This comparison is observational; a 20% region publish is the proof."
)


def _history() -> list[dict]:
    """60 ended contracts: even i had a proposal (lapsed when i % 6 == 0), odd i none (renewed when i % 3 == 0); US below 40."""
    out = []
    for i in range(60):
        with_p = i % 2 == 0
        renewed = i % 6 != 0 if with_p else i % 3 == 0
        out.append(
            {"contractId": f"FC-H{i:03d}", "market": "US" if i < 40 else "DE", "lines": 4, "endedAt": "2026-09-01",
             "outcome": "renewed" if renewed else "lapsed", "hadProposal": with_p, "feeBefore": 1000.0, "feeAfter": 1100.0}
        )  # fmt: skip
    return out


@pytest.fixture
def seen(monkeypatch):
    """The 60 rows are the fleet's history, and the history belongs to the workspace."""
    monkeypatch.setattr(contract_history, "rows", lambda s: _history())
    monkeypatch.setattr(renewals, "history_org", lambda s: "workspace")


def _contract(status: str | None, fee: float | None = None) -> None:
    facts = [canonical.Fact("contract", "FC-30140", "renewal_status", status, resource="contracts")]
    if fee is not None:
        facts.append(canonical.Fact("contract", "FC-30140", "fee_month", fee, resource="contracts"))
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts)
        s.commit()


def _sent_proposal(cid: str) -> None:
    """The case's approved proposal as it was sent: one swap, one keep, a fee of 120 a month, a 0.8 chance of renewal."""
    doc = {"route": "proposal", "fee_month_current": 110.0, "fee_month_proposed": 120.0, "renewal_likelihood": 0.8,
           "lines": [{"serial": "FC-30140-S00", "action": "swap"}, {"serial": "FC-30140-S01", "action": "keep"}]}  # fmt: skip
    with SessionLocal() as s:
        c = store.get(s, cid, for_update=True)
        assert c is not None
        c["exec"] = {"proposal": doc, "steps": []}
        c["refreshProposal"] = {"proposal": doc}
        store.save(s, c)
        s.commit()


def _record() -> list[str]:
    with SessionLocal() as s:
        out = refresh_outcome.record(s)
        s.commit()
    return out


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _report(acct: str = "admin", **q) -> dict:
    r = client.get("/api/screens/analytics/renewals", params={"since": "2024-10-08", "until": "2026-10-07"} | q, headers=h(acct))
    assert r.status_code == 200, r.text
    return r.json()


def test_cr_07_outcome_recorded_on_case(refresh_case):  # noqa: F811
    assert _record() == []  # the contract is still open: nothing to record
    _sent_proposal(refresh_case)
    _contract("renewed", 118.0)
    assert _record() == [refresh_case]
    o = _case(refresh_case)["renewalOutcome"]
    assert o["renewed"] is True and o["fee_after"] == 118.0 and o["fee_before"] == 110.0 and o["swaps_accepted"] == 1
    assert o["predicted"] == {"likelihood": 0.8, "fee_month": 120.0} and o["had_proposal"] is True
    assert _record() == []  # once: a second sync records nothing again and keeps the first


def test_cr_07_a_lapse_is_recorded_without_a_fee(refresh_case):  # noqa: F811
    _sent_proposal(refresh_case)
    _contract("lapsed")
    assert _record() == [refresh_case]
    o = _case(refresh_case)["renewalOutcome"]
    assert o["renewed"] is False and o["fee_after"] is None and o["swaps_accepted"] == 0


def test_cr_07_rates_with_and_without_proposal(seen):
    r = _report()
    assert (r["with_proposal"]["n"], r["with_proposal"]["renewed"]) == (30, 20)
    assert (r["without_proposal"]["n"], r["without_proposal"]["renewed"]) == (30, 10)
    assert r["with_proposal"]["rate"] == pytest.approx(20 / 30) and r["without_proposal"]["rate"] == pytest.approx(10 / 30)
    seg = {(x["market"], x["size"]): x for x in r["segments"]}
    assert set(seg) == {("US", "small"), ("DE", "small")}
    assert [(seg[k]["with_proposal"]["n"], seg[k]["with_proposal"]["renewed"]) for k in sorted(seg)] == [(10, 7), (20, 13)]
    assert [(seg[k]["without_proposal"]["n"], seg[k]["without_proposal"]["renewed"]) for k in sorted(seg)] == [(10, 3), (20, 7)]


def test_cr_07_closed_case_joins_the_comparison(seen, refresh_case):  # noqa: F811
    _sent_proposal(refresh_case)
    _contract("renewed", 132.0)
    _record()
    r = _report()
    assert (r["with_proposal"]["n"], r["with_proposal"]["renewed"]) == (31, 21)
    c = r["compared"]
    assert c["n"] == 1 and c["predicted_rate"] == pytest.approx(0.8) and c["actual_rate"] == pytest.approx(1.0)
    assert c["fee_error_pct"] == pytest.approx(10.0)  # 132 against the 120 proposed
    assert c["swaps_accepted"] == 1


def test_cr_07_the_period_bounds_the_rows(seen):
    r = _report(since="2026-09-02", until="2026-10-07")
    assert r["with_proposal"]["n"] == 0 and r["with_proposal"]["rate"] is None and r["segments"] == []


def test_cr_07_caveat_shown(seen):
    r = _report()
    assert r["caveat"] == CAVEAT
    assert r["basis"].startswith("observed")  # the fleet's own ended contracts, never the prototype's modelled 90% and 81%


def test_cr_07_tenant_boundary(seen, refresh_case):  # noqa: F811
    _sent_proposal(refresh_case)
    _contract("renewed", 118.0)
    _record()
    assert _report("admin")["with_proposal"]["n"] == 31
    r = client.get(
        "/api/screens/analytics/renewals", params={"since": "2024-10-08", "until": "2026-10-07"}, headers=h("planner-b")
    )
    if r.status_code == 200:  # the account's own units only: neither the workspace's history nor tool-fleet-a's case
        assert r.json()["with_proposal"]["n"] == 0 and r.json()["without_proposal"]["n"] == 0
    else:
        assert r.status_code == 403  # no analytics page at all


def test_cr_07_outcomes_by_unit(seen, refresh_case):  # noqa: F811
    _sent_proposal(refresh_case)
    _contract("renewed", 118.0)
    _record()
    with SessionLocal() as s:
        here = renewals.outcomes(s, [ORG], date(2024, 10, 8), TODAY)
        none = renewals.outcomes(s, ["customer-b"], date(2024, 10, 8), TODAY)
    assert [
        (x.contract_id, x.market, x.size_band, x.had_proposal, x.renewed, x.fee_before, x.fee_after, x.swaps_accepted)
        for x in here
    ] == [("FC-30140", "US", "small", True, True, 110.0, 118.0, 1)]
    assert none == []
