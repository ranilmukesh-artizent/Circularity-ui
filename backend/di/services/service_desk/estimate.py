"""The estimate from similar past repairs on each line of a service-desk case (plan 9, P9-4.4, story SD-02; uses I-14 and I-15).

    gr_s1() -> GrS1Params                          the estimate guardrail's numbers, from the pack
    estimate_line(s, case, line, as_of) -> Estimate  one line: the history, today's cards, the model; a draft books the check
    estimate_case(s, case, as_of)                    every line, stamped on the case's line snapshot (`lines[n].estimate`)

- **Computed, never read by a model (R16).** The estimate is `di.services.models.cost.RepairCostModel` over rows and rate cards:
  every number, and every number in the reason, is computed. There is no model step here: the reason and the technician
  question are fixed phrases filled from those numbers and the serial, and nothing reads the ticket's free text.
- **History.** The closed repairs of the case's org (and the shared rows) for the line's class and fault, closed in
  `[as_of - window_years, as_of)`, read once per class and fault for the whole case. **Cards.** The approved labour, parts and
  terms cards of the ticket's market in force on `as_of` (the org's own version first, else the shared one); the lines cite them.
  A market without cards is a draft, not a failure: the case still opens and a technician prices it.
- **Held-out accuracy (P9-4.5).** A class whose newest `repair_accuracy` row (the org's, else the shared one) has `instant` false
  is never priced without a technician: the estimate keeps its figures, `auto` is false and the reason names the held-out
  coverage (or error) and the bar. The row's coverage is the estimate's `confidence`; with no row it stays 0.80.
- **Technician check.** A draft books one `needs_info` work item of type `technician_check` for the Engineer role per line,
  "Technician check: post the fault for <serial>", through `cases.process.open_item` (the same item `case.needInfo` opens, I-20);
  evaluating the line again finds it and books no second.
- **Fault posted (P9-4.7).** `serviceDesk.postFault` estimates the line again with the code and closes its check item; the
  estimate then names no item. The check stays the same row (`check_item` finds it by title), so a draft never books a second.
- **Stored, so decisions repeat (R19).** `estimate_case` writes the estimate onto the line, so `decide_case` reads the same facts
  on a second run. The page reads `serviceDesk.lines[*].estimate` from the case.

Never does: delete, approve or release anything, add an action, or open a case (intake does).
"""

from collections.abc import Mapping, MutableMapping
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import market_tables as tables_repo
from di.repositories import repair_accuracy as accuracy_repo
from di.repositories import rollouts
from di.repositories.repair_accuracy import AccuracyRow
from di.repositories.repair_history import RepairRow, similar
from di.services.cases import process
from di.services.modeler.pack import load_pack
from di.services.modeler.tables import market_spec, rate_card
from di.services.models.cost import FLOW, PACK, Estimate, GrS1Params, PriceCards, RepairCostModel, RepairKey, age_band, unpriced

ROLE = "Engineer"
CHECK = "technician_check"
CARDS = ("labour", "parts", "terms")
FAULTS = ("MOT", "GBX", "ELE", "WEA")  # the depot's fault codes: motor, gearbox, electronics, wear parts
History = dict[tuple[str | None, str, str, date, date], list[RepairRow]]


def gr_s1() -> GrS1Params:
    """GR-S1: at least `min_matches` similar repairs, a range of at most `max_width_share` of the point, `window_years` back."""
    p = load_pack(PACK).valuer.params["service_desk"]["gr_s1"]
    return GrS1Params(int(p["min_matches"]), Decimal(str(p["max_width_share"])), int(p["window_years"]))


def _off(acc: AccuracyRow) -> str:
    """Why a family is not priced instantly: its newest held-out figures against GR-S1's bar."""
    p = load_pack(PACK).valuer.params["service_desk"]["gr_s1"]
    least, most = Decimal(str(p["min_coverage"])), Decimal(str(p["max_mae_share"]))
    off = "Instant pricing is off for this family: held-out"
    if acc.coverage < least:
        return f"{off} coverage {acc.coverage * 100:.0f}% is under the {least * 100:.0f}% bar"
    return f"{off} error {acc.mae_share * 100:.0f}% is over the {most * 100:.0f}% bar"


def _since(as_of: date, years: int) -> date:
    try:
        return as_of.replace(year=as_of.year - years)
    except ValueError:  # 29 February
        return as_of.replace(year=as_of.year - years, day=28)


def _cards(s: Session, org: str | None, market: str, as_of: date) -> PriceCards | None:
    tables_repo.ensure_seeded(s, PACK)
    rows = [tables_repo.effective(s, org, PACK, FLOW, market, name, as_of) for name in CARDS]
    if any(r is None for r in rows):
        return None
    return PriceCards(*(rate_card(r) for r in rows if r is not None))


def _title(line: Mapping[str, Any]) -> str:
    return f"Technician check: post the fault for {line['serial']}"


def check_item(s: Session, case_id: str, line: Mapping[str, Any]) -> int | None:
    """The technician-check item booked for this line, if any."""
    r = s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND title = :ti ORDER BY id LIMIT 1"),
        {"c": case_id, "t": CHECK, "ti": _title(line)},
    ).scalar()
    return None if r is None else int(r)


def _book_check(s: Session, case: Mapping[str, Any], line: Mapping[str, Any], reason: str) -> None:
    cid = str(case["id"])
    if check_item(s, cid, line) is not None:
        return
    process.open_item(
        s, kind="needs_info", case_id=cid, org_unit_id=case.get("owner"), type=CHECK, title=_title(line), cause=reason,
        action="Post the fault on the repair order", owner_role=ROLE, due_hours=process.sla_hours(s, cid, "needs_info"),
        by="service desk",
    )  # fmt: skip


def estimate_line(
    s: Session, case: Mapping[str, Any], line: Mapping[str, Any], as_of: date, *, history: History | None = None
) -> Estimate:
    """The estimate of one line on `as_of`; a draft books the technician check once (module docstring). `history` is the
    case's shared read, so lines with the same class and fault read the rows once."""
    params = gr_s1()
    market = str((case.get("serviceDesk") or {}).get("market") or "")
    org = case.get("owner")
    cls, fault = str(line["model_class"]), line.get("fault_code") or None
    read = rollouts.table_version_for(s, case)[0] if market else market  # the market whose tables price it (P9-7.7: FR canary)
    cards = _cards(s, org, read, as_of) if market else None
    if cards is None:
        why = f"No rate cards for market {market or 'unknown'} on {as_of.isoformat()}: draft, a technician checks"
        spec = market_spec(PACK)
        e = unpriced(why, "class_fault_age", 0, spec.markets.get(market, "") if spec else "", 0.80)
    else:
        rows: list[RepairRow] = []
        if fault is not None:
            key = (org, cls, fault, _since(as_of, params.window_years), as_of)
            cache = history if history is not None else {}
            if key not in cache:
                cache[key] = similar(s, org, cls, fault, None, key[3], key[4])
            rows = cache[key]
        band = age_band(line.get("age_months")) or ""
        acc = accuracy_repo.latest(s, org, cls)
        e = RepairCostModel().estimate(
            rows, RepairKey(cls, fault, band), cards, params, None if acc is None else float(acc.coverage)
        )
        if e.auto and acc is not None and not acc.instant:
            e = replace(e, auto=False, reason=_off(acc))
    if not e.auto:
        _book_check(s, case, line, e.reason)
    return e


def as_dict(e: Estimate, as_of: date, item: int | None) -> dict[str, Any]:
    """The estimate as the case keeps it (JSON): money as numbers, the lines with what each cites, the check item if any."""
    return {
        "point": float(e.point), "p10": float(e.p10), "p90": float(e.p90), "n": e.n, "key_used": e.key_used,
        "lines": [{"label": ln.label, "amount": float(ln.amount), "basis": ln.basis, "cites": ln.cites} for ln in e.lines],
        "auto": e.auto, "reason": e.reason, "confidence": e.confidence, "currency": e.currency, "as_of": as_of.isoformat(),
        "item": item,
    }  # fmt: skip


def estimate_case(s: Session, case: MutableMapping[str, Any], as_of: date) -> None:
    """Estimate every line of the case and keep each on its line (`lines[n].estimate`). The caller saves the case."""
    base = case.get("serviceDesk")
    if not isinstance(base, dict):
        return
    history: History = {}
    for line in base["lines"]:
        e = estimate_line(s, case, line, as_of, history=history)
        line["estimate"] = as_dict(e, as_of, None if e.auto else check_item(s, str(case["id"]), line))
