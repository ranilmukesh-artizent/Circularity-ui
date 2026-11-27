"""A contract with a battery line (class BAT) in its refresh window is priced like the others: the daily scan opens its case
with routes and a proposal, and one such contract does not stop the scan of the rest (the market's terms carry a list price
for BAT; the scan failed with `KeyError: ... has no rate list_price.BAT` and opened no case at all). Starts and ends with the
demo reset."""

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.canonical import store as canonical
from di.services.cases import refresh_intake, store
from tests import refreshkit as rk
from tests import starting
from tests.helpers import call

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

LINES = [("CMH-Z1", "CMH", 12), ("BAT-Z2", "BAT", 12)]


@pytest.fixture
def scanned():
    starting.reset()
    call("org.create", {"id": rk.ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")
    rk.forget()
    c = {"contract_id": "FC-39001", "customer": "Battery Works", "market": "US", "start_date": "2024-01-05",
         "end_date": "2027-01-05", "term_months": 36, "status": "active"}  # fmt: skip
    facts = [canonical.Fact("contract", "FC-39001", k, v, resource="contracts") for k, v in c.items()]
    for serial, cls, months in LINES:
        f = {"contract_id": "FC-39001", "serial": serial, "tool_class": cls, "model": f"{cls}-12", "fee_month": 55.0,
             "months_on_contract": months, "status": "on_contract", "line_id": "FL-" + serial}  # fmt: skip
        facts += [canonical.Fact("contract_line", serial, k, v, resource="lines") for k, v in f.items()]
    with SessionLocal() as s:
        canonical.apply(s, "fleet", facts)
        s.commit()
    with SessionLocal() as s:
        ids = refresh_intake.scan(s, rk.ORG, rk.TODAY)
        s.commit()
    yield ids
    rk.forget()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM case_record WHERE owner = :o"), {"o": rk.ORG})
        s.commit()
    starting.reset()


def test_a_battery_line_is_priced_in_the_refresh(scanned):
    assert len(scanned) == 1
    with SessionLocal() as s:
        c = store.get(s, scanned[0])
    assert c is not None
    assert c["routes"] and c["refreshProposal"] and "refreshBlock" not in c
    assert {x["serial"] for x in c["refresh"]["lines"]} == {"CMH-Z1", "BAT-Z2"}
