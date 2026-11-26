"""Non-return fees of closed contract lines (plan 9, P9-3.18, story TF-14; registry entries I-11 and I-20).

    closed_lines(s) -> [line]                       the fleet's lines that closed without the tool and carry a fee
    value_line(line) -> {type, label, basis, amt}   the fee as a value line (the contract's own figure)
    raise_items(s) -> [item id]                     one `non_return` item for the Fleet desk per such line (I-20)
    line_row(s, line_id) -> line | None             one line by its line id (the canonical `contract_line`)
    item_of(s, line_id) -> item | None              the line's item, open or closed
    post(s, line_id, by) -> dict                    a person posts the fee: one `nonreturnfee` instruction, the item closes

A line the fleet contract system moved to `closed_not_returned` with a non-return fee raises one
exception item for the Fleet desk (role Planner), once per line (`raise_items`, called after each sync of the source by
`FleetContractsAdapter.after_sync`). The fee is the contract line's own `nonReturnFee`, read from the canonical store when it is
shown and again when it is posted; no model reads or writes anything here (R16: it is arithmetic on a contract figure).

Posting goes through the instruction queue like every write to an executing system: `post` inserts one instruction (kind
`nonreturnfee`, system `erp`, idempotent on the line and the amount in cents) and its `instruction.send` job, whose writer is
`writers_fleet.fee_post` (a journal entry to SAP S/4HANA). The fee has no case and no approval plan, so the instruction is its
own, like a device payout: `send.send` builds a stand-in case from the instruction's detail (line, serial, owning org).
Who posts: the action `nonReturnFee.post` (permission `postFees`); an agent's call is held for a person (HELD_FOR_PERSON, I-10).
Never does: post without a person (or the standing policy), change the fee, or reopen an item that was closed.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock, jobs
from di.services.cases import process

EXCEPTION = "non_return"
KIND = "nonreturnfee"  # the instruction's kind (and its writer)
SYSTEM = "erp"  # SAP S/4HANA, the billing writer `finance` uses
STATUS = "closed_not_returned"
PACK = "tool_fleet"
BASIS = "contract fee for a tool not returned"


def title_of(line_id: str) -> str:
    return f"Non-return fee {line_id}"


def _line(key: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "line_id": str(data.get("line_id") or ""), "serial": key, "status": data.get("status"),
        "fee": float(data.get("non_return_fee") or 0), "contract_id": data.get("contract_id"),
    }  # fmt: skip


def closed_lines(s: Session) -> list[dict[str, Any]]:
    """The lines that closed without the tool and have a fee above zero, by serial."""
    rows = s.execute(
        text("SELECT key, data FROM canonical WHERE model = 'contract_line' AND data ->> 'status' = :st ORDER BY key"),
        {"st": STATUS},
    ).all()
    lines = [_line(r.key, r.data or {}) for r in rows]
    return [x for x in lines if x["line_id"] and x["fee"] > 0]


def line_row(s: Session, line_id: str) -> dict[str, Any] | None:
    r = s.execute(
        text("SELECT key, data FROM canonical WHERE model = 'contract_line' AND data ->> 'line_id' = :l"), {"l": line_id}
    ).first()
    return _line(r.key, r.data or {}) if r else None


def value_line(line: dict[str, Any]) -> dict[str, Any]:
    return {"type": "v", "label": title_of(line["line_id"]), "basis": BASIS, "amt": line["fee"]}


def org_of(s: Session, serial: str, contract_id: str | None = None) -> str | None:
    """The org unit that owns the fee (its work and the tenant boundary follow it): the `owner_org` of the line's contract, else
    the owner of the tool's latest case, or None when neither is on file (a tenant-scoped person is then refused, R21)."""
    if contract_id:
        owner = s.execute(
            text("SELECT data ->> 'owner_org' FROM canonical WHERE model = 'contract' AND key = :k"), {"k": contract_id}
        ).scalar()
        if owner:
            return str(owner)
    return s.execute(
        text("SELECT owner FROM case_record WHERE data ->> 'assetId' = :a ORDER BY id DESC LIMIT 1"), {"a": serial}
    ).scalar()


def item_of(s: Session, line_id: str) -> dict[str, Any] | None:
    r = (
        s.execute(
            text("SELECT * FROM work_item WHERE type = :t AND title = :ti ORDER BY id DESC LIMIT 1"),
            {"t": EXCEPTION, "ti": title_of(line_id)},
        )
        .mappings()
        .first()
    )
    return dict(r) if r else None


def raise_items(s: Session) -> list[int]:
    """One `non_return` item per closed line that has none yet (open or closed: a posted fee is not raised again). In the
    caller's transaction."""
    from di.services.modeler.pack import load_pack  # lazy: the pack loader imports the valuers

    pack = load_pack(PACK)
    kind = next((t for t in pack.runtime.exception_types if t.id == EXCEPTION), None)
    out: list[int] = []
    for line in closed_lines(s):
        if item_of(s, line["line_id"]) is not None:
            continue
        v = value_line(line)
        out.append(
            process.open_item(
                s, kind="exception", case_id=None, org_unit_id=org_of(s, line["serial"], line["contract_id"]),
                type=EXCEPTION,
                title=title_of(line["line_id"]),
                cause=f"Contract line {line['line_id']} closed without the tool {line['serial']}. {v['label']}: {v['basis']}, "
                f"${v['amt']:,.0f}.",
                action=kind.action if kind else "Post the contract's non-return fee",
                owner_role=process.role_of_owner(kind.owner_role if kind else "Fleet desk"),
                due_hours=pack.runtime.sla_hours.get("exception"), by="system",
            )
        )  # fmt: skip
    return out


def stand_in_case(ins: dict[str, Any]) -> dict[str, Any]:
    """What the writer and the pilot check read in place of a case: the fee's own id, its org and the tool."""
    d = ins.get("detail") or {}
    return {
        "id": ins["case_id"], "owner": d.get("org") or "workspace", "template": PACK, "assetId": d.get("serial"),
        "location": "", "exec": None,
    }  # fmt: skip


def post(s: Session, line_id: str, by: str) -> dict[str, Any]:
    """A person posts the line's fee: queue the instruction (only when sending instructions is switched on, as for a payout) and
    close the item. The fee is read from the canonical line now, not from the item. In the caller's transaction."""
    from di.services.instructions import queue  # the queue imports the execution layer

    line = line_row(s, line_id)
    if line is None or line["status"] != STATUS or line["fee"] <= 0:
        raise LookupError(f"Line {line_id} has no non-return fee to post.")
    cents = int(round(line["fee"] * 100))
    ref, key = f"FEE-{line_id}", f"FEE.{line_id}.{cents}"
    iid = None
    if queue.enabled():
        org = org_of(s, line["serial"], line["contract_id"])
        detail = {"line_id": line_id, "serial": line["serial"], "fee": line["fee"], "org": org, "by": by}
        iid = s.execute(
            text(
                "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, detail, queued_at) "
                "VALUES (:c, :r, 0, :k, :sys, :key, CAST(:refs AS jsonb), CAST(:d AS jsonb), :at) "
                "ON CONFLICT (idem_key) DO NOTHING RETURNING id"
            ),
            {
                "c": ref, "r": ref, "k": KIND, "sys": SYSTEM, "key": key, "refs": json.dumps([key]), "d": json.dumps(detail),
                "at": clock.now(),
            },
        ).scalar()  # fmt: skip
        if iid is not None:
            jobs.enqueue(s, "instruction.send", {"instruction_id": iid})
    item = item_of(s, line_id)
    if item is not None and item["status"] == "open":
        process.close_item(s, int(item["id"]), f"Fee posted: ${line['fee']:,.0f}", by)
    return {
        "line_id": line_id, "serial": line["serial"], "fee": line["fee"], "instruction": int(iid) if iid is not None else None,
        "item": int(item["id"]) if item else None,
        "log": f"Non-return fee posted for {line_id}: ${line['fee']:,.0f}"
        + ("" if iid is not None else " (instructions are off: nothing sent)"),
    }  # fmt: skip
