"""The fixed-asset close of a pack that owns its assets (plan 9, P9-13.1, story X-13; registry entries I-6, I-11).

    retire     SAP S/4HANA (`erp`)  POST /sap/bc/srt/scs_ext/sap/fixedassetretirement {assetKey, retirementDate, proceeds,
                                    currency, externalReference}: the asset leaves the books with its proceeds
    transfer   SAP S/4HANA (`erp`)  POST /sap/bc/srt/scs_ext/sap/fixedassettransfer {assetKey, transferDate, toLocation,
                                    externalReference}: the asset moves to the site or cost centre of the route

The proceeds are the realised value an earlier step's acknowledgement reported (`detail.proceeds`), else the decision's value
line (the route's positive sale terms). The external reference is the approval reference, sent also as the idempotency key,
so a resend answers the first asset document. The ERP's answer (document, proceeds, book value, gain or loss) is kept on the
instruction as `detail.asset`; the acknowledgement copies it to `case["finance"]["asset"]` (`di.services.execution.asset`).

Never does: compute the gain or loss (the ERP does; Finance owns the retirement), pick a route, or approve. The endpoint names
are modelled, not verified, against SAP's fixed-asset posting services. Accounting references are for orientation only: Finance
and Kinective's Legal team confirm them before anyone relies on them.
"""

from typing import Any

from sqlalchemy.orm import Session

from di.connectors.http import SourceError
from di.core import clock
from di.services.cases import store
from di.services.instructions import writers
from di.services.instructions.writers import NotApplicable, Refused, Sent, _refused

RETIRE = "/sap/bc/srt/scs_ext/sap/fixedassetretirement"
TRANSFER = "/sap/bc/srt/scs_ext/sap/fixedassettransfer"
CURRENCY = "USD"


def _key(c: store.Case) -> str:
    """The asset's key in the ERP's fixed-asset master: the car's VIN, else the unit's serial or tag."""
    key = (c.get("vehicle") or {}).get("vin") or str(c.get("serial") or c.get("assetId") or "").rpartition(":")[2]
    if not key:
        raise NotApplicable("no asset key to post for")
    return str(key)


def _proceeds(c: store.Case, prev: dict) -> float:
    for row in prev.values():
        got = (row.get("detail") or {}).get("proceeds")
        if isinstance(got, int | float) and not isinstance(got, bool):
            return float(got)
    r = c.get("chosen") or c.get("recommendation") or {}
    return float(sum(t["amt"] for t in r.get("terms") or [] if t.get("kind") in ("sale", "salvage") and t["amt"] > 0))


def _post(s: Session, path: str, ins: dict, body: dict[str, Any]) -> dict[str, Any]:
    cl = writers.client(s, "erp")
    try:
        return dict(cl.request("POST", path, json=body, headers={"Idempotency-Key": ins["idem_key"]}).json())
    except SourceError as e:
        raise _refused(e) from e
    finally:
        cl.close()


def _asset(kind: str, doc: dict[str, Any]) -> dict[str, Any]:
    out = {"kind": kind, "doc": doc["assetDocument"], "at": clock.now().isoformat()}
    if kind == "retire":
        out |= {k: doc.get(f) for k, f in (("proceeds", "proceeds"), ("book_value", "bookValue"), ("gain_loss", "gainLoss"))}
        out["currency"] = doc.get("currency") or CURRENCY
    return out


def retire(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:
    body = {
        "assetKey": _key(c), "retirementDate": clock.now().date().isoformat(), "proceeds": _proceeds(c, prev),
        "currency": CURRENCY, "externalReference": c["exec"]["ref"],
    }  # fmt: skip
    doc = _post(s, RETIRE, ins, body)
    if not doc.get("assetDocument"):
        raise Refused("The ERP returned no asset document for the retirement")
    return Sent([{"call": f"POST {RETIRE.lstrip('/')}", "body": body}], doc["assetDocument"],
                {"confirmed": True, "proceeds": body["proceeds"], "asset": _asset("retire", doc)})  # fmt: skip


def transfer(s: Session, ins: dict, c: store.Case, prev: dict) -> Sent:  # noqa: ARG001 - every writer takes (session, instruction, case, previous)
    dest = (c.get("chosen") or c.get("recommendation") or {}).get("dest") or {}
    to = dest.get("site") or dest.get("region")
    if not to:
        raise Refused("The route names no site or cost centre to transfer the asset to")
    body = {
        "assetKey": _key(c), "transferDate": clock.now().date().isoformat(), "toLocation": to,
        "externalReference": c["exec"]["ref"],
    }  # fmt: skip
    doc = _post(s, TRANSFER, ins, body)
    if not doc.get("assetDocument"):
        raise Refused("The ERP returned no asset document for the transfer")
    return Sent([{"call": f"POST {TRANSFER.lstrip('/')}", "body": body}], doc["assetDocument"],
                {"confirmed": True, "asset": _asset("transfer", doc)})  # fmt: skip
