"""Carrying out an approved service-desk option on market terms (plan 9, P9-4.9, story SD-05; registry entries I-6, I-10, I-11).

    on_approve(s, case)              in `decision.approve`'s transaction: the market terms are kept on the approved plan
                                     (`exec.terms`) and the refurbished unit of every covered swap is reserved
    on_takeback(s, case, step)       when the `takeback` step is acknowledged: a Returns case opens for each old tool taken back
                                     and the credit goes (the next step, queued by `instructions.on_acknowledged`)
    terms_of(case, on) -> dict       the market terms of the approval date `on`

The plan itself is the existing execution plan: the route carries the step kinds and the lines each covers (`valuers.service_desk.
step_plan`), `steps_for` makes the steps, the instruction queue sends them in order and every instruction carries the terms in
its `detail.terms`. A split has one sale order for its upgrade lines, one service reference for its fix lines and one delivery to
the site; nothing is built beside that path.

- **Terms.** `market`, the references of the price list, the labour rate and the credit rule the options were priced on (the table
  versions the case cites, I-15) and `valid_until`, the approval date plus the market's `proposal_valid_days` (14).
- **Reserve.** At approval each swap line takes one refurbished unit of its class (`refurb_stock.reserve`); the unit is kept on
  the line (`reserved_unit`). When the stock ran out since the options were valued the approval is refused with `conflict`.
- **Takeback.** The old tool's Returns case is opened through `cases.intake.open_case` (reason `trade_in`, the serial as the asset
  key, `flow` `returns`, `source_case` the service case), so a second acknowledgement finds the first case and opens none.

No model step (R16): the plan, the terms and every journal line are computed. Never does: approve, release or send anything for
a person (the approval is a person's or the standing policy's, and the credit step is sent by the instruction queue after the
takeback, as a step of an approved plan); no new action, so nothing joins FORBIDDEN_ACTIONS.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.repositories import refurb_stock
from di.services.actions.registry import ActionError
from di.services.cases import store

TERM_TABLES = ("parts prices", "labour rates", "credit rules")  # the price list, the labour rate and the credit rule


def terms_of(c: dict[str, Any], on: date) -> dict[str, Any] | None:
    """The market terms the case's options were priced on, valid from `on`; None for a case without options."""
    sd = c.get("serviceDesk")
    inputs = sd.get("inputs") if isinstance(sd, dict) else None
    if not inputs:
        return None
    refs = [r for name in TERM_TABLES for r in inputs.get("approved") or [] if name in r]
    days = int(inputs["lines"][0]["terms"].get("proposal_valid_days", 14))
    return {
        "market": inputs["market"],
        "refs": refs,
        "approved_on": on.isoformat(),
        "valid_until": (on + timedelta(days=days)).isoformat(),
    }


def stale_tables(s: Session, c: dict[str, Any], on: date) -> list[str]:
    """GR-S3 at the approval: the table versions the case's options cite that are not the approved ones in force on `on`
    (none for a case that is not a service ticket).
    The terms' `valid_until` runs from `on`."""
    from di.services.service_desk import inputs  # lazy: inputs reads the repositories

    return inputs.stale_refs(s, c, on)


def _unit(s: Session, org: str | None, model_class: str) -> str | None:
    row = s.execute(
        text(
            "SELECT serial FROM refurb_unit WHERE model_class = :c AND reserved_case IS NULL "
            "AND (org_unit_id IS NULL OR org_unit_id = :o) ORDER BY serial LIMIT 1 FOR UPDATE SKIP LOCKED"
        ),
        {"c": model_class, "o": org},
    ).first()
    return row[0] if row else None


def on_approve(s: Session, c: dict[str, Any]) -> None:
    """Keep the market terms on the approved plan and reserve the unit of each swap line (module docstring). No commit."""
    sd, x = c.get("serviceDesk"), c.get("exec")
    if not isinstance(sd, dict) or not x:
        return
    if terms := terms_of(c, clock.now().date()):
        x["terms"] = terms
    for step in x["steps"]:
        if step["k"] != "reserve":
            continue
        for n in step.get("lines") or []:
            line = next(ln for ln in sd["lines"] if ln["n"] == n)
            unit = _unit(s, c.get("owner"), line["model_class"])
            if unit is None or not refurb_stock.reserve(s, unit, c["id"]):
                raise ActionError("conflict", f"No refurbished {line['model_class']} is left to reserve for {line['serial']}.")
            line["reserved_unit"] = unit


def _journal(s: Session, c: dict[str, Any], line: str) -> None:
    """A line in the case's stage log (the journal the case page shows)."""
    stage = str(c.get("stage") or "none")
    s.execute(
        text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor) VALUES (:c, :st, :st, :r, 'system')"),
        {"c": c["id"], "st": stage, "r": line},
    )


def on_takeback(s: Session, c: dict[str, Any], step: int) -> list[str]:
    """The old tools of the `takeback` step are in: open a Returns case for each (a repeat opens none) and journal it with the
    release of the credit when the plan has one. Returns the ids opened. In the caller's transaction."""
    from di.services.cases import intake  # intake does not import this package; the hook runs after it is loaded

    sd, x = c["serviceDesk"], c["exec"]
    st = x["steps"][step]
    credit = any(k["k"] == "credit" for k in x["steps"])
    opened: list[str] = []
    for n in st.get("lines") or [ln["n"] for ln in sd["lines"]]:
        line = next(ln for ln in sd["lines"] if ln["n"] == n)
        try:
            with s.begin_nested():
                case = intake.open_case(
                    s,
                    {"org_unit_id": c["owner"], "template_key": "tool_fleet", "asset_key": line["serial"], "reason": "trade_in",
                     "by": "service desk",
                     "facts": {"cls": line["model_class"], "serial": line["serial"], "age": line["age_months"],
                               "ft": "Repair center", "flow": "returns", "source_case": c["id"]}},
                    "system",
                )  # fmt: skip
                case["source_case"] = c["id"]
                store.save(s, case)
        except ActionError as e:
            if e.code != "duplicate":
                raise
            continue  # the acknowledgement came twice: the first opened the case
        opened.append(case["id"])
        _journal(s, c, f"Taken-back {line['serial']} opened {case['id']} in Returns" + ("; credit released" if credit else ""))
    return opened
