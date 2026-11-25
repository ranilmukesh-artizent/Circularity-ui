"""One case per service ticket or batch (plan 9, P9-4.3, story SD-01; builds the facts `decide_case`, I-6, decides on).

    ticket_case(case_id, ticket) -> facts        the case facts of a ticket: its account, market and site, `batch`, and one
                                                 line per tool with its life used
    line_gates(s, line, owner_org, ...) -> [..]  the two checks of one line: GR-07 contract right, GR-12 safety recall
    view(s, case) -> dict | None                 what the case page's Ticket tab shows (the lines with their gate results)
    open_from_ticket(s, ticket, actor, ...)      the case of one ticket, through `cases.intake.open_case` (the only intake)
    open_pending(s, org, actor) / open_all_pending(s, actor)   the `sdesk` adapter's post-sync hook

- **One case per ticket.** The asset key is the ticket number and the reason `service_ticket`, so `open_case`'s dedupe (asset key
  and reason) refuses a second case for the same ticket ("RT-n is already open for CS0010042 (service_ticket)."). A batch ticket
  (`batch_id` set) is one case that keeps every line, in the ticket's order.
- **Life used.** `round(age_months / rated_months x 100)`, half up, with `rated_months` from the pack
  (`valuer.params.service_desk`: CMH 48, BRK 48, DCD 60, CRH 36, AGR 36, LSR 60). A class the pack does not know is a
  `validation_error`. (A tool with a remaining-life fact from the telematics adds it with the estimate, P9-4.4.)
- **Two gates on every line.** The contract line the fleet contract system holds for the serial (`fleet_evidence.contract_check`,
  GR-07) and the register's notices (`fleet_evidence.recall_check`, GR-12) are read for each line, and the page shows each line's
  result with the reason. The case itself is valued and gated as one tool: the valuer reads the *worst* line (no contract first,
  then a recall, else the first), so the existing gates hold it (`no_active_contract` for the Fleet desk) or quarantine it
  (`recall_quarantine` for Quality, no priced option for the blocked routes) from the line that needs a person.
- **Hook.** After each `sdesk` sync the adapter calls `open_all_pending`: every pending ticket of an org whose tool-fleet flow is
  published opens its case, in a savepoint inside the sync's session (a dry or failed run undoes the cases with the rows, and a
  refused ticket stays pending without failing the sync). A ticket of a source bound to no org unit has no owner for its case and
  stays pending.

No model step (R16): the fault code, cover and age are structured fields and the free text of a fault is carried to the page as
the customer wrote it, never read, summarised or copied into the journal. Never does: write outside the caller's session, delete,
approve or release anything (no new action), or open a case by another path than `cases.intake.open_case`.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories.flows import flow_for
from di.repositories.service_tickets import TicketRow, pending
from di.services.actions.registry import ActionError
from di.services.cases import contract_line, recall_evidence, store
from di.services.engine.jsmath import js_round
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import fleet_evidence, tool_fleet

PACK = "tool_fleet"
REASON = "service_ticket"
FLOW = "service_desk"
FT = "Repair center"  # the function a ticket's tool goes to
LINE_FIELDS = ("serial", "model_class", "age_months", "fault_code", "fault_text", "cover_type", "cover_until")
GATES = (fleet_evidence.GATE, fleet_evidence.RECALL_GATE)
RATED: dict[str, int] = dict(load_pack(PACK).valuer.params["service_desk"]["rated_months"])


def life_used_pct(model_class: str, age_months: int | float) -> int:
    """The share of the tool's rated life its age uses (module docstring); `validation_error` for an unknown class."""
    if model_class not in RATED:
        raise ActionError("validation_error", f"Unknown tool class {model_class}: one of {', '.join(RATED)}.")
    return int(js_round(age_months / RATED[model_class] * 100))


def ticket_case(case_id: str, ticket: TicketRow) -> dict[str, Any]:  # noqa: ARG001 - the case id: the spec's signature
    """The case facts of a ticket: `flow`, `ticket` (its number), `account`, `market`, `site`, `batch` (many tools), the
    `loaner_promised` flag and one line per tool with `n`, the ticket's fields and `life_used_pct`."""
    lines = [
        {"n": n, **{k: ln.get(k) for k in LINE_FIELDS},
         "life_used_pct": life_used_pct(str(ln.get("model_class")), ln.get("age_months") or 0)}
        for n, ln in enumerate(ticket.lines, 1)
    ]  # fmt: skip
    if not lines:
        raise ActionError("validation_error", f"Ticket {ticket.number} has no tool lines.")
    return {
        "flow": FLOW, "ticket": ticket.number, "account": ticket.account, "market": ticket.market,
        "site": ticket.site, "batch": ticket.batch_id is not None, "batch_id": ticket.batch_id,
        "requester_role": ticket.requester_role, "loaner_promised": ticket.loaner_promised, "lines": lines,
    }  # fmt: skip


# ---------------------------------------------------------------- the two gates of a line
def line_gates(
    s: Session, line: Mapping[str, Any], owner_org: str, release: Mapping[str, Any] | None = None,
    recalls: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:  # fmt: skip
    """The result of GR-07 and GR-12 for one line: `[{id, name, guardrail, passed, reason}]`. `release` is the person's release
    of the tool's recall (a case's `recallRelease`); `recalls` the register's notices when the caller has read them already."""
    serial, cls = str(line.get("serial") or ""), str(line.get("model_class") or "")
    found = contract_line.evidence(s, serial)
    contract = fleet_evidence.contract_check(found["value"] if found else None, owner_org, serial)
    notices = recalls if recalls is not None else recall_evidence.evidence(s, cls, None)["value"]["recalls"]
    recall, _, _ = fleet_evidence.recall_check(serial, cls, notices, release)
    return [
        {"id": contract.gate_id, "name": "Contract right", "guardrail": "GR-07", "passed": contract.passed,
         "reason": contract.reason},
        {"id": recall.gate_id, "name": "Safety recall", "guardrail": "GR-12", "passed": recall.passed, "reason": recall.reason},
    ]  # fmt: skip


def _worst(s: Session, lines: Sequence[Mapping[str, Any]], owner_org: str) -> Mapping[str, Any]:
    """The line the case is valued and gated on: the first without a contract right, else the first under a recall, else the
    first line."""
    checked = [(ln, {g["id"]: g["passed"] for g in line_gates(s, ln, owner_org)}) for ln in lines]
    for gate in GATES:
        for ln, ok in checked:
            if not ok[gate]:
                return ln
    return lines[0]


def view(s: Session, case: Mapping[str, Any]) -> dict[str, Any] | None:
    """The `serviceDesk` block of a case page (facade `serviceDeskView`): the ticket and its lines, each with the tool family's
    name and its gate results as they are now. None for a case that is not a service-desk case."""
    base = case.get("serviceDesk")
    if case.get("flow") != FLOW or not isinstance(base, dict):
        return None
    pack = load_pack(PACK)
    notices = recall_evidence.evidence(s, None, None)["value"]["recalls"]
    own = case.get("recallRelease") if isinstance(case.get("recallRelease"), dict) else None
    return {
        "ticket": base["ticket"], "account": base["account"], "market": base["market"], "site": base["site"],
        "batch": bool(base["batch"]), "batchId": base.get("batch_id"), "loanerPromised": bool(base.get("loaner_promised")),
        "requesterRole": base.get("requester_role"),
        "lines": [
            ln | {"family": tool_fleet.CLS.get(ln["model_class"], {}).get("name", ln["model_class"]),
                  "gates": line_gates(s, ln, pack.owner or "", own if ln["serial"] == case.get("serial") else None, notices)}
            for ln in base["lines"]
        ],
    }  # fmt: skip


# ---------------------------------------------------------------- open
def open_from_ticket(s: Session, ticket: TicketRow, actor: str, org_unit_id: str | None = None) -> store.Case:
    """Open the case of one ticket (module docstring) in the caller's transaction and stamp `service_ticket.case_id`.
    `org_unit_id` is the org that owns the case when the ticket names none (a shared one). ActionError when refused: a
    duplicate, an unknown class, a ticket with no org unit."""
    from di.services.cases import intake  # intake does not import this package; the hook runs after it is loaded

    org = ticket.org_unit_id or org_unit_id
    if org is None:
        raise ActionError("validation_error", f"Ticket {ticket.number} has no org unit.")
    facts = ticket_case("", ticket)  # also refuses an unknown class before anything is written
    gate_org = load_pack(PACK).owner or ""
    top = _worst(s, facts["lines"], gate_org)
    case = intake.open_case(
        s,
        {"org_unit_id": org, "template_key": PACK, "asset_key": ticket.number, "reason": REASON, "by": "service desk",
         "facts": {"cls": top["model_class"], "serial": top["serial"], "age": top["age_months"], "ft": FT, "flow": FLOW,
                   "serviceDesk": facts}},
        actor,
    )  # fmt: skip
    s.execute(text("UPDATE service_ticket SET case_id = :c WHERE number = :n"), {"c": case["id"], "n": ticket.number})
    return case


def open_pending(s: Session, org_unit_id: str, actor: str = "system") -> list[str]:
    """Open a case for every pending ticket of the org whose tool-fleet flow is published; the ids opened. A refused ticket
    stays pending and does not stop the others. In the caller's transaction."""
    if flow_for(s, PACK, org_unit_id) is None:
        return []
    opened: list[str] = []
    for t in pending(s, org_unit_id):
        if t.org_unit_id is None:
            continue  # nobody owns the case: the source is bound to no org unit
        try:
            with s.begin_nested():
                case = open_from_ticket(s, t, actor)
        except ActionError:
            continue
        opened.append(case["id"])
    return opened


def open_all_pending(s: Session, actor: str = "system") -> list[str]:
    """`open_pending` for every org that has a pending ticket (the adapter's hook); the ids opened."""
    orgs = s.execute(
        text("SELECT DISTINCT org_unit_id FROM service_ticket WHERE case_id IS NULL AND org_unit_id IS NOT NULL ORDER BY 1")
    ).scalars()
    return [cid for org in list(orgs) for cid in open_pending(s, org, actor)]
