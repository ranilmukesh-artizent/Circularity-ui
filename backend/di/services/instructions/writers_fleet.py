"""The tool fleet's two writes to its own systems (plan 9, P9-3.17, story TF-10; registry entries I-6, I-11).

    fleet_issue   the `lease` step of a re-issue (`release`): PATCH the contract line of the named renewal with the issued serial
                  fleet contract system  PATCH /contract-lines/{lineId}  {status: "issued", issuedSerial, issuedKey, issuedFor}
    parts_issue   the `partsxfer` step of a harvest: post each certified part to its open repair order
                  parts and service system  PATCH /repair-orders/open/{roId}
                  {status: "part_issued", issuedPart, issuedFrom, issuedKey}

Both are writers of the existing instruction queue (`writers.WRITERS`, chosen by `writers.write_kind` for a tool-fleet case):
the same contract as every writer (`Sent`; a business refusal is `Refused`, a case with nothing to write `NotApplicable`),
idempotent on the instruction key, which the writes carry as `issuedKey` and the mocks' update event returns, so
`instructions.events` acknowledges the step from it. Nothing is built beside the queue.

- **fleet_issue.** The renewal is the route's destination (`dest.id`, a fleet renewal such as FC-30117-R); its contract's
  lines are read and the line the tool comes off is the one written: the returned line of the renewal's tool class that
  carries the tool's own serial, else the first returned line of that class (by line id). A line already `issued` to this
  serial is a repeat: nothing is written again.
- **parts_issue.** The repair orders are the harvest route's `dest.wos`; the part is the one each order is waiting for
  (its `partName`). An order already holding this tool's part is left as it is.

Never does: approve or send for a person (the plan was approved by a person or the standing policy and the queue sends it),
read the database, or write language (no model step, R16). A source read-only here is refused by the queue before a writer runs
(P9-0.14); the connected-tool unlink before a re-issue (GR-11) is a known gap, not a story.
"""

from sqlalchemy.orm import Session

from di.connectors.http import SourceError
from di.services.cases import store
from di.services.instructions import writers
from di.services.instructions.writers import NotApplicable, Refused, Sent

FLEET = "/fleet/api/v1"
PARTS = "/parts/api"


def _refused(e: SourceError) -> Exception:
    """A 4xx other than auth is a business refusal; anything else is retried (as `writers._refused`)."""
    return Refused(str(e)) if e.kind == "client" else e


def _line_of(lines: list[dict], serial: str, cls: str) -> dict | None:
    """The line to issue (module docstring): the tool's own returned line, else the first returned line of its class."""
    returned = sorted(
        (x for x in lines if x.get("status") == "returned" and x.get("toolClass") == cls), key=lambda x: x["lineId"]
    )
    return next((x for x in returned if x.get("serial") == serial), returned[0] if returned else None)


def fleet_issue(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """The contract line of the named renewal is issued with the tool's serial (module docstring)."""
    route = c.get("chosen") or c["recommendation"]
    dest = route.get("dest") or {}
    renewal, serial = str(dest.get("id") or "").strip(), c["assetId"]
    if dest.get("kind") != "lease" or not renewal:
        raise NotApplicable("no named fleet renewal to issue the tool to")
    cl = writers.client(s, "fleet")
    try:
        ren = cl.get_json(f"{FLEET}/renewals/{renewal}")
        lines = cl.get_json(f"{FLEET}/contract-lines", params={"contractId": ren["contractId"], "limit": 100})["items"]
        done = next((x for x in lines if x.get("status") == "issued" and x.get("issuedSerial") == serial), None)
        if done:  # sent before: the line is issued to this tool already
            return Sent([], done["lineId"], {"lineId": done["lineId"], "renewal": renewal, "serial": serial, "duplicate": True})
        line = _line_of(lines, serial, str(ren.get("toolClass")))
        if line is None:
            raise Refused(
                f"No returned {ren.get('toolClass')} line on contract {ren['contractId']} to issue {serial} to for {renewal}"
            )
        body = {"status": "issued", "issuedSerial": serial, "issuedKey": ins["idem_key"], "issuedFor": renewal}
        cl.request("PATCH", f"{FLEET}/contract-lines/{line['lineId']}", json=body)
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(
        [{"call": "PATCH contract-lines/{lineId}", "body": body}], line["lineId"],
        {"lineId": line["lineId"], "renewal": renewal, "contract": ren["contractId"], "serial": serial},
    )  # fmt: skip


def parts_issue(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    """Each certified part is posted to its open repair order (module docstring)."""
    route = c.get("chosen") or c["recommendation"]
    orders = [str(x) for x in (route.get("dest") or {}).get("wos") or []]
    serial = c["assetId"]
    if not orders:
        raise NotApplicable("no open repair order to post a part to")
    calls: list[dict] = []
    cl = writers.client(s, "parts")
    try:
        for ro in orders:
            doc = cl.get_json(f"{PARTS}/repair-orders/open/{ro}")
            if doc.get("status") == "part_issued" and doc.get("issuedFrom") == serial:
                continue  # sent before
            body = {
                "status": "part_issued",
                "issuedPart": doc.get("partName"),
                "issuedFrom": serial,
                "issuedKey": ins["idem_key"],
            }
            cl.request("PATCH", f"{PARTS}/repair-orders/open/{ro}", json=body)
            calls.append({"call": "PATCH repair-orders/open/{roId}", "body": body})
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()
    return Sent(calls, orders[-1], {"orders": orders, "serial": serial, "duplicate": not calls})
