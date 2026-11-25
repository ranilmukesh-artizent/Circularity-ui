"""One case per received device (plan 9, P9-6.4, story DV-01; builds the facts `decide_case`, I-6, decides on).

Owns: `device_case` (a trade-in and its facts as the device valuer's lot), `lot_case` (a bulk batch as a PO-shaped lot with
a line per device), `intake_facts` (the facts `cases.intake.open_case` builds a device case from), `open_from_tradein` and
`open_pending` (the lab adapter's post-sync hook).
- A trade-in with `bulk` false opens one case, `asset_key` `IMEI:<imei>`, reason `trade_in`, quantity 1. The reference value
  is the market feed's price for the SKU and grade as of today (its week and staleness are kept in `valuer.inputs`); with no
  price it is the quote's amount (`ref_source` "quote"). The grade is the lab's cosmetic grade when it has graded the
  device, else the one declared at the quote.
- A bulk trade-in opens one lot case per `batch_id` (`asset_key` the batch id): its lines, a lot valued as a PO lot (no
  `imei`, so the four PO channels): grade the lines' most common, quantity the lines, the reference value their mean.
- Dedupe is `cases.intake`'s (asset key and reason); a refused duplicate or a device the valuer cannot value (a model it
  does not know) leaves the trade-in pending. A case opened stamps `device_tradein.case_id` of its trade-ins.
Never does: read a source (the lab adapter landed the rows), write outside the caller's session (a dry run is rolled back
with it), value a channel (the valuer does), or open a case of another template. `cases.intake` is the only intake.
Model first (R16): nothing here reads or writes language, so there is no model call; every figure is computed.
"""

from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories import device_market, device_tradeins
from di.repositories.device_tradeins import TradeInRow
from di.repositories.flows import flow_for
from di.services.actions.registry import ActionError
from di.services.canonical import store as canonical
from di.services.cases import store
from di.services.device.inputs import imei_key
from di.services.modeler.valuers import device

TEMPLATE = "device"
REASON = "trade_in"
GRADES = ("A", "B", "C", "D")
# the fields of a device case that its valuer snapshot keeps beside the lot's own (cases.intake.device_lot)
EXTRA = (
    "imei", "sku_key", "storage_gb", "graded", "declared_grade", "ref_source", "quote", "partner", "batch_id", "received",
    "lines",
)  # fmt: skip


def _model_row(model: str) -> list[Any]:
    row = next((m for m in device.DMOD if m[1] == model), None)
    if row is None:
        raise ActionError("validation_error", f"The device model {model} is not one the valuer knows.")
    return row


def _grade(t: TradeInRow, facts: Mapping[str, Any]) -> tuple[str, bool]:
    """(the grade the device is valued on, whether the lab graded it): the cosmetic grade when graded, else the declared."""
    cosmetic = facts.get("cosmetic_grade")
    if cosmetic in GRADES:
        return str(cosmetic), True
    declared = (t.quote or {}).get("declaredGrade")
    if declared not in GRADES:
        raise ActionError("validation_error", "A trade-in needs a declared grade (A-D) or a cosmetic grade from the lab.")
    return str(declared), False


def tradein_facts(s: Session, t: TradeInRow, as_of: datetime) -> dict[str, Any]:
    """What a trade-in's case reads beyond the row: the lab's cosmetic grade (canonical `condition`) and the feed's price for
    its SKU and grade as of `as_of`."""
    cond = (canonical.get(s, "condition", imei_key(t.imei)) or {}).get("data") or {}
    facts: dict[str, Any] = {"as_of": as_of.isoformat(), "cosmetic_grade": cond.get("cosmetic_grade")}
    grade, _ = _grade(t, facts)
    point = device_market.feed_price(s, f"{t.sku['model']}|{t.sku['storageGb']}", grade, as_of.date())
    if point:
        facts |= {"feed_price": point.price, "feed_week": point.week.isoformat(), "feed_stale": point.stale}
    return facts


def device_case(case_id: str, tradein: TradeInRow, facts: Mapping[str, Any]) -> dict[str, Any]:
    """The device valuer's lot for one received device. `facts`: `as_of` (ISO time), and from `tradein_facts` the
    `cosmetic_grade`, `feed_price`, `feed_week`. ActionError `validation_error` for a model or grade the valuer does not know
    or a trade-in with neither a feed price nor a quote."""
    sku = tradein.sku
    row = _model_row(str(sku["model"]))
    grade, graded = _grade(tradein, facts)
    quote = dict(tradein.quote or {})
    if facts.get("feed_price") is not None:
        ref, source = float(facts["feed_price"]), "feed"
    elif isinstance(quote.get("amount"), int | float):
        ref, source = float(quote["amount"]), "quote"
    else:
        raise ActionError("validation_error", "A trade-in needs a quote amount when the market feed has no price for it.")
    as_of = datetime.fromisoformat(str(facts["as_of"]))
    return {
        "id": case_id, "imei": tradein.imei, "sku_key": f"{sku['model']}|{sku['storageGb']}", "brand": sku.get("brand") or row[0],
        "model": sku["model"], "storage_gb": sku["storageGb"], "band": row[3], "grade": grade, "graded": graded,
        "declared_grade": quote.get("declaredGrade"), "ref": ref, "ref_source": source, "qty": 1,
        "doh": max(0, (as_of - tradein.received_at).days), "quote": quote, "partner": tradein.partner,
        "batch_id": tradein.batch_id, "received": tradein.received_at.isoformat(),
    }  # fmt: skip


def _common(values: list[str]) -> str:
    """The most common value, the first in sort order on a tie."""
    return sorted(Counter(values).items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def lot_case(rows: list[TradeInRow], as_of: datetime, s: Session) -> dict[str, Any]:
    """A bulk batch as a PO-shaped lot (no `imei`): `lines` one per device, grade their most common, `qty` their number,
    `ref` their mean reference value, `doh` the oldest line's days on hand."""
    cases = [device_case("", t, tradein_facts(s, t, as_of)) for t in rows]
    model = _common([c["model"] for c in cases])
    top = next(c for c in cases if c["model"] == model)
    lines = [
        {"imei": c["imei"], "model": c["model"], "storage_gb": c["storage_gb"], "declared_grade": c["declared_grade"],
         "grade": c["grade"], "ref": c["ref"], "quote": (c["quote"] or {}).get("amount")}
        for c in cases
    ]  # fmt: skip
    return {
        "brand": top["brand"], "model": model, "band": top["band"], "grade": _common([c["grade"] for c in cases]),
        "ref": round(sum(c["ref"] for c in cases) / len(cases), 2), "qty": len(cases), "doh": max(c["doh"] for c in cases),
        "partner": _common([c["partner"] for c in cases]), "batch_id": rows[0].batch_id, "lines": lines,
        "received": min(c["received"] for c in cases),
    }  # fmt: skip


def intake_facts(s: Session, case_id: str, facts: Mapping[str, Any]) -> dict[str, Any]:
    """The facts a device case opens with, for a trade-in on file for `facts["imei"]` (what `case.open` with `trade_in`
    and an IMEI gives); the caller's own facts win."""
    row = device_tradeins.by_imei(s, str(facts["imei"]))
    if row is None:
        raise ActionError("validation_error", f"No trade-in was received for IMEI {facts['imei']}.")
    return device_case(case_id, row, tradein_facts(s, row, clock.now())) | dict(facts)


def open_from_tradein(s: Session, tradein: TradeInRow, actor: str) -> store.Case:
    """Open the case for a received trade-in (module docstring) in the caller's transaction, and stamp its trade-ins. A
    duplicate, a trade-in with no org unit or a device the valuer cannot value is refused (ActionError)."""
    from di.services.cases import intake  # intake imports this package for the device facts

    if tradein.org_unit_id is None:
        raise ActionError("validation_error", f"Trade-in {tradein.trade_in_id} has no org unit.")
    facts: dict[str, Any]
    if tradein.bulk and tradein.batch_id:
        rows = device_tradeins.by_batch(s, tradein.batch_id)
        key, facts = tradein.batch_id, lot_case(rows, clock.now(), s)
    else:
        rows, key, facts = [tradein], imei_key(tradein.imei), {"imei": tradein.imei}
    case = intake.open_case(
        s, {"org_unit_id": tradein.org_unit_id, "template_key": TEMPLATE, "asset_key": key, "reason": REASON, "facts": facts},
        actor,
    )  # fmt: skip
    s.execute(
        text("UPDATE device_tradein SET case_id = :c WHERE trade_in_id = ANY(:ids)"),
        {"c": case["id"], "ids": [r.trade_in_id for r in rows]},
    )
    return case


def open_all_pending(s: Session, actor: str = "system") -> list[str]:
    """`open_pending` for every org that has a pending trade-in (the lab adapter's hook); the ids opened."""
    orgs = s.execute(
        text("SELECT DISTINCT org_unit_id FROM device_tradein WHERE case_id IS NULL AND org_unit_id IS NOT NULL ORDER BY 1")
    ).scalars()
    return [cid for org in list(orgs) for cid in open_pending(s, org, actor)]


def open_pending(s: Session, org_unit_id: str, actor: str = "system") -> list[str]:
    """Open a case for every pending trade-in of the org (one per IMEI, one per bulk batch) whose device flow is published;
    the ids opened. A trade-in that is refused stays pending, and does not stop the others. In the caller's transaction."""
    if flow_for(s, TEMPLATE, org_unit_id) is None:
        return []
    opened: list[str] = []
    done: set[str] = set()
    for t in device_tradeins.pending(s, org_unit_id):
        if t.org_unit_id is None or (t.bulk and t.batch_id in done):
            continue
        try:
            with s.begin_nested():
                case = open_from_tradein(s, t, actor)
        except ActionError:
            continue
        opened.append(case["id"])
        if t.bulk and t.batch_id:
            done.add(t.batch_id)
    return opened
