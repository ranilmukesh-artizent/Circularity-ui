"""Service booking (plan 9, P9-11.7, story MR-06): a person books certification or maintenance for a rental device.

    service.book   act   {case_id, asset_tag, kind, due_by}   bookService (Admin, Engineer, Planner): a service order for the
                                                               device, on the case and, when instructions are on, in `mr_biomed`

The gate G-MED-SVC proposes it (`case["serviceCheck"]["proposed"]`) when a unit's certification or preventive maintenance ends
before a rental does. `kind` is `pm`, `certification`, `repair` or `refurbish` (the service system's); the asset tag is the
case's device; `due_by` an ISO date. The order is kept on the case as `serviceOrders` (the same tag, kind and date again is a
duplicate) and, with DI_INSTRUCTIONS on, written to the biomedical service system (`POST /service-orders`, idempotent there on
tag, kind and date); with it off, as in the test suite, nothing leaves di. The pipeline refuses another tenant's case.

An agent may prepare it but never run it: `service.book` is in HELD_FOR_PERSON (I-10), so an agent's call becomes a proposal a
person accepts. It approves, clears and waives nothing, so it is not in FORBIDDEN_ACTIONS (the gate itself is cleared only by
evidence). No model step (R16): the action reads the case and writes one order.
"""

from datetime import date
from typing import Any

from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import store

SOURCE = "mr_biomed"
KINDS = ("pm", "certification", "repair", "refurbish")

ACTIONS.setdefault(
    "service.book",
    ActionDef(
        id="service.book", title="Book service for a rental device", verb="book service",
        desc="Book certification, preventive maintenance, a repair or a refurbishment for a rental device with the biomedical "
        "service system. An agent's call is held for a person.",
        risk="act", perm="bookService", scope="case",
        input={
            "case_id": {"req": True, "t": "string"},
            "asset_tag": {"req": True, "t": "string"},
            "kind": {"req": True, "t": "string"},
            "due_by": {"req": True, "t": "string"},
        },
    ),
)  # fmt: skip


def _key(i: dict[str, Any]) -> str:
    return f"{i['case_id']}:{i['asset_tag']}:{i['kind']}:{i['due_by']}"


@guard("service.book")
def book_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    c = store.get(ctx.session, i["case_id"])
    if c is None or c.get("template") != "medical_rental":
        return "not_found", f"No live rental case {i['case_id']}."
    if i["kind"] not in KINDS:
        return "validation_error", f"Unknown service kind {i['kind']}. Use one of {', '.join(KINDS)}."
    if str(c.get("assetId") or "").split(":", 1)[-1] != i["asset_tag"]:
        return "validation_error", f"{i['asset_tag']} is not the device of {i['case_id']}."
    try:
        date.fromisoformat(str(i["due_by"]))
    except ValueError:
        return "validation_error", f"due_by must be a date (YYYY-MM-DD), not {i['due_by']}."
    if any(o["key"] == _key(i) for o in c.get("serviceOrders") or []):
        return "duplicate", f"{i['kind']} is already booked for {i['asset_tag']} by {i['due_by']}."
    return None


@implement("service.book", idem=lambda i, ctx: _key(i))  # noqa: ARG005 - the key is the input
def book(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    from di.services.instructions import queue
    from di.services.instructions.writers import client

    c = store.get(ctx.session, i["case_id"], for_update=True)
    if c is None:
        raise ActionError("not_found", f"No live rental case {i['case_id']}.")
    orders = list(c.get("serviceOrders") or [])
    order = {
        "key": _key(i), "order_id": None, "asset_tag": i["asset_tag"], "kind": i["kind"], "due_by": i["due_by"], "source": SOURCE,
        "by": ctx.actor.id, "at": ctx.now.isoformat(), "sent": False,
    }  # fmt: skip
    if queue.enabled():  # the service system's order is idempotent on tag, kind and date
        from di.connectors.http import SourceError

        cl = client(ctx.session, SOURCE)
        try:
            r = cl.request("POST", "/service-orders", json={"tag": i["asset_tag"], "kind": i["kind"], "dueBy": i["due_by"]})
            order |= {"order_id": r.json().get("orderId"), "sent": True}
        except SourceError as e:
            raise ActionError("conflict", f"The service system did not take the order: {e}") from e
        finally:
            cl.close()
    c["serviceOrders"] = [*orders, order]
    store.save(ctx.session, c)
    where = "sent to the service system" if order["sent"] else "recorded on the case"
    return {
        "case_id": c["id"], "asset_tag": i["asset_tag"], "kind": i["kind"], "due_by": i["due_by"], "sent": order["sent"],
        "order_id": order["order_id"], "log": f"Booked {i['kind']} for {i['asset_tag']} by {i['due_by']}: {where}",
    }  # fmt: skip
