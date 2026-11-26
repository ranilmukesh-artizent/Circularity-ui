"""The customer credit of a trade-in or upgrade, and its match against the ERP (plan 9, P9-13.4, story X-16; registry entries
I-6 and I-20).

Pure (nothing read or written):
    credit_amount(case, pack) -> Credit | None   what the case says the customer is credited: the payout the device pack adjusted
                                                 (DV-05, `case["payout"]["adjusted"]`, basis `requote`), else the quote times the
                                                 pack's `close.credit_table` percent for the grade received (basis `grade_table`);
                                                 None when the pack has no credit settlement, the case no quote, or no payout
                                                 that is final nor a received grade in the table (nothing is assumed)
    matches(case_amount, erp_amount) -> bool     equal to the cent

On the case (in the caller's transaction):
    record(s, c, step) -> bool                   on the acknowledgement of the `credit` step: `case["finance"]["credit"]` from the
                                                 instruction's `detail.credit` (the ERP's memo and the amount it posted); False
                                                 when the ERP amount differs, then one I-20 item (TITLE)
                                                 is opened for Finance and the caller keeps the case `executing`
    close_item(s, case_id, outcome, by)          closes that item once Finance has answered (`settlement.resolve`,
                                                 di.services.actions.execution)
    waiting(c) -> bool                           the ERP's credit differs and nobody has answered

Money is `Decimal`. Never does: post anything (the writer `credit` does), pick the amount the ERP posted, or approve. No model
step (R16): arithmetic and fixed sentences. Accounting references are for orientation only: Finance and Kinective's Legal team
confirm them before anyone relies on them.
"""

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.modeler.pack import Pack

KIND = "credit"
EXCEPTION = "credit_mismatch"
TITLE = "ERP credit differs from the case"
ACTION = "Check the credit memo in the ERP; accept the ERP amount or send the credit again."
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Credit:
    amount: Decimal
    currency: str
    basis: Literal["requote", "grade_table", "core_acceptance"]
    grade_declared: str | None
    grade_received: str | None
    quote: Decimal | None
    requote_ref: str | None


def _dec(v: Any) -> Decimal | None:
    return None if isinstance(v, bool) or not isinstance(v, int | float | Decimal | str) or v == "" else Decimal(str(v))


def _cents(v: Any) -> Decimal:
    return Decimal(str(v)).quantize(CENT, ROUND_HALF_UP)


def matches(case_amount: Any, erp_amount: Any) -> bool:
    """True when both amounts are the same to the cent."""
    return _cents(case_amount) == _cents(erp_amount)


def _quote(case: Mapping[str, Any]) -> tuple[Decimal, str] | None:
    q = (case.get("valuer") or {}).get("quote") or case.get("quote")
    if not isinstance(q, Mapping) or (amount := _dec(q.get("amount"))) is None:
        return None
    return _cents(amount), str(q.get("currency") or "USD")


def credit_amount(case: Mapping[str, Any], pack: Pack) -> Credit | None:
    """The credit the case says (module docstring); a payout that still waits for a person is not an amount yet."""
    if not pack.close.credit_settlement:
        return None
    if isinstance(case.get("core"), Mapping):
        return _core_credit(case, pack)
    if (got := _quote(case)) is None:
        return None
    quote, currency = got
    lot, pay = case.get("valuer") or {}, case.get("payout") or {}
    declared = pay.get("inputs", {}).get("declared_grade") or lot.get("declared_grade") or case.get("declared_grade")
    received = pay.get("inputs", {}).get("actual_grade") or lot.get("received_grade") or case.get("received_grade")
    if pay:
        adjusted = _dec(pay.get("adjusted")) if pay.get("status") in ("adjusted", "decided") else None
        if adjusted is None:
            return None
        return Credit(_cents(adjusted), currency, "requote", declared, received, quote, pay.get("table"))
    pct = pack.close.credit_table.get(str(received))
    if pct is None:
        return None
    return Credit(_cents(quote * Decimal(str(pct)) / 100), currency, "grade_table", declared, received, quote, None)


def _core_credit(case: Mapping[str, Any], pack: Pack) -> Credit | None:
    """A returned core (automotive cores pack, P9-13.6, NS-CORE-02): the deposit times the acceptance share the pack's gate gives
    (full 100 %, partial 50 %, none 0, `core_credit`); the quote field holds the deposit. None without a deposit."""
    from di.services.modeler.gate_checks.core import core_credit  # lazy: the gate checks import the modeler

    core = case["core"]
    deposit = _dec(core.get("deposit"))
    if deposit is None:
        deposit = _dec(case.get("deposit"))
    if deposit is None:
        return None
    got = core_credit(core, pack)
    return Credit(_cents(deposit * got["pct"] / 100), "USD", "core_acceptance", None, got["credit"], _cents(deposit), None)


def money(v: Any) -> str:
    return f"${_cents(v):,.2f}"


def basis_line(credit: Mapping[str, Any]) -> str:
    """ "grade B at 80 % of the $200.00 quote", or the adjusted payout's own words, for the case page."""
    if credit.get("basis") == "core_acceptance":
        return f"core accepted with {credit.get('grade_received')} credit of the {money(credit['quote'])} deposit"
    if credit.get("basis") == "requote":
        return (
            f"payout adjusted from the {money(credit['quote'])} quote" if credit.get("quote") is not None else "payout adjusted"
        )
    pct = credit.get("percent")
    got = f"grade {credit.get('grade_received')}" + (f" at {pct:g} %" if pct is not None else "")
    return got + (f" of the {money(credit['quote'])} quote" if credit.get("quote") is not None else "")


# ---------------------------------------------------------------- on a case
def record(s: Session, c: MutableMapping[str, Any], step: int) -> bool:
    """Copy the ERP's answer for the `credit` step to the case and match it; see the module docstring. A step the system
    acknowledged with no answer (a simulated one) leaves the case as it was and counts as matched."""
    row = s.execute(
        text("SELECT detail FROM instruction WHERE case_id = :c AND step = :n AND approval_ref = :r"),
        {"c": c["id"], "n": step, "r": c["exec"]["ref"]},
    ).first()
    got = ((row[0] if row else None) or {}).get("credit")
    if not isinstance(got, dict) or got.get("memo") is None:
        return True
    ok = matches(got["amount"], got["erp_amount"])
    c["finance"] = {**(c.get("finance") or {}), "credit": {**got, "status": "matched" if ok else "mismatch",
                                                            "realised": got["erp_amount"] if ok else None}}  # fmt: skip
    if not ok:
        _open_item(s, c, got)
    return ok


def _open_item(s: Session, c: Mapping[str, Any], got: Mapping[str, Any]) -> int | None:
    from di.services.cases import process

    cid = str(c["id"])
    if s.execute(
        text("SELECT 1 FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"), {"c": cid, "t": EXCEPTION}
    ).first():
        return None
    return process.open_item(
        s, kind="exception", case_id=cid, org_unit_id=c.get("owner"), type=EXCEPTION, title=TITLE,
        cause=f"The case says {money(got['amount'])}; the ERP posted {money(got['erp_amount'])} on credit memo {got['memo']}.",
        action=ACTION, owner_role="Finance", due_hours=None, by="system",
    )  # fmt: skip


def close_item(s: Session, case_id: str, outcome: str, by: str) -> None:
    from di.services.cases import process

    for (iid,) in s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open'"), {"c": case_id, "t": EXCEPTION}
    ).all():
        process.close_item(s, int(iid), outcome, by)


def waiting(c: Mapping[str, Any]) -> bool:
    """True while the ERP's credit differs from the case's and Finance has not answered."""
    return ((c.get("finance") or {}).get("credit") or {}).get("status") == "mismatch"
