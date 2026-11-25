"""The payout adjustment of a received device (plan 9, P9-6.8, story DV-05; the market tables are registry entry I-15, the work
item is I-20).

    evaluate(row, inputs) -> TableResult           the pack's decision table `payout_rules` run on the grading facts (ZEN)
    assess_payout(quote, outputs, ...) -> Payout   the adjusted amount and the gap, computed from the quote and the table's result
    facts_of(s, case) -> dict | None               the table's inputs: declared and actual grade, battery, functional fails
    assess_case(s, case, pack)                     value the payout once the lab has graded the device and read its battery
    flush(s, case)                                 write the journal line of a payout assessed before the case row existed
    decided(s, case, ...)                          record a person's decision (`payout.decide`) and send it
    view(s, case) -> dict | None                   the case page's `payout`

When the lab has graded the device (`condition.cosmetic_grade`) and read its battery (`battery_health_pct`), the table
`payout_rules` (market US, from `valuer.params.market_tables` of the device pack) returns an `adjust_pct` and a `reason`; the
adjusted payout is the quote times one plus that share, in cents. A gap of at most `max_auto_gap` (the pack's guardrail GR-D11,
10 percent) is adjusted at once (`payout.status` "adjusted"), journaled as "Payout adjusted -6% ($410 -> $385.40): <reason> (US
payout rules v1)" and sent to the trade-in platform as a `payout` instruction (idempotent on the case and the amount; the
writer is `instructions.writers.payout`). A bigger gap waits ("waiting"): a `payout_gap` item for Customer care (role Planner)
names the grading photos, the rule and the table version, and nothing is sent until a person decides it with `payout.decide`
(a person's action: in FORBIDDEN_ACTIONS; "decided").
Never does: decide a payout that waits, raise one above the quote, change the table (a person approves a table version,
`marketTable.*`) or write to a system without the instruction queue. A payout stands once it is on the case: a later valuation
does not change it.
Model first (R16): the amount, the gap and the reason are computed from the quote and the table; the texts are fixed wording
over those numbers. Nothing here drafts or explains, so there is no model call.
"""

from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock, jobs
from di.repositories import market_tables as tables_repo
from di.services.canonical import store as canonical
from di.services.cases import process, store
from di.services.modeler import tables
from di.services.modeler.pack import Pack

PACK = "device"
TABLE = "payout_rules"
GUARDRAIL = "GR-D11"
EXCEPTION = "payout_gap"
OWNER_LABEL = "Customer care"  # the owner label of GR-D11 (role Planner)
KIND = "payout"  # the instruction's step kind
GRADES = ("A", "B", "C", "D")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class Payout:
    """The computed payout: `quote`, `adjusted` and `gap_pct` (Decimals), the table's `reason`, what it `cites` and `auto`."""

    quote: Decimal
    adjusted: Decimal
    gap_pct: Decimal
    reason: str
    cites: tuple[str, ...]
    auto: bool


# ---------------------------------------------------------------- pure
def max_auto_gap(pack: Pack) -> Decimal:
    """The pack's limit for an automatic adjustment (guardrail GR-D11's `max_auto_gap`)."""
    g = next((x for x in pack.guardrails if x.id == GUARDRAIL), None)
    return Decimal(str(g.param.value)) if g is not None and g.param is not None else Decimal("0.10")


def evaluate(row: tables_repo.TableRow, inputs: Mapping[str, Any]) -> tables.TableResult:
    """The table's result on `inputs` (the stored version `row`, run by the ZEN evaluator)."""
    return tables.ZenEvaluator().evaluate(tables.JdmTable.model_validate(row.body), inputs)


def assess_payout(
    quote: Mapping[str, Any], outputs: Mapping[str, Any], *, max_auto_gap: Decimal, cites: tuple[str, ...] = ()
) -> Payout:
    """The payout the table's `outputs` (`adjust_pct`, `reason`) give for the quote `{amount, currency}`; `auto` when the gap is
    at most `max_auto_gap` either way. The adjusted amount is rounded to cents."""
    amount = Decimal(str(quote["amount"]))
    gap = Decimal(str(outputs["adjust_pct"]))
    adjusted = (amount * (Decimal(1) + gap)).quantize(CENT, ROUND_HALF_UP)
    return Payout(amount, adjusted, gap, str(outputs["reason"]), cites, abs(gap) <= max_auto_gap)


def money(v: Decimal | float) -> str:
    """ "$410" for a whole amount, "$385.40" otherwise."""
    d = Decimal(str(v)).quantize(CENT)
    return f"${d:,.0f}" if d == d.to_integral_value() else f"${d:,.2f}"


def share(v: Decimal | float) -> str:
    """The signed share as a percentage: -0.06 -> "−6%", 0 -> "0%"."""
    p = (Decimal(str(v)) * 100).normalize()
    return ("−" if p < 0 else "+" if p > 0 else "") + f"{abs(p):f}%"


def adjusted_line(p: Mapping[str, Any]) -> str:
    return f"Payout adjusted {share(p['gap_pct'])} ({money(p['quote'])} → {money(p['adjusted'])}): {p['reason']} ({p['table']})"


def waiting_line(p: Mapping[str, Any], limit: Decimal) -> str:
    return (
        f"Payout adjustment {share(p['gap_pct'])} ({money(p['quote'])} → {money(p['adjusted'])}) is above the "
        f"{share(limit).lstrip('+')} limit: {p['reason']} ({p['table']}); waits for {OWNER_LABEL}"
    )


# ---------------------------------------------------------------- on a case
def _lot(case: Mapping[str, Any]) -> dict[str, Any] | None:
    v = case.get("valuer")
    return v if isinstance(v, dict) and v.get("imei") else None


def _number(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def facts_of(s: Session, case: Mapping[str, Any]) -> dict[str, Any] | None:
    """The table's inputs for a received device, or None while the lab has not graded it, read its battery or the trade-in has
    no declared grade or quote (nothing is assumed): `declared_grade`, `actual_grade`, `battery_pct` (a whole percent),
    `functional_fails` (how many), and the `photos` the grading names, the `quote` and its `currency`."""
    lot = _lot(case)
    if lot is None:
        return None
    cond = (canonical.get(s, "condition", f"IMEI:{lot['imei']}") or {}).get("data") or {}
    quote = lot.get("quote") or {}
    battery, amount = _number(cond.get("battery_health_pct")), _number(quote.get("amount"))
    declared, actual = lot.get("declared_grade"), cond.get("cosmetic_grade")
    if battery is None or amount is None or declared not in GRADES or actual not in GRADES:
        return None
    fails = cond.get("functional_fails")
    return {
        "declared_grade": declared, "actual_grade": actual,
        "battery_pct": int(Decimal(str(battery)).quantize(Decimal(1), ROUND_HALF_UP)),
        "functional_fails": len(fails) if isinstance(fails, list | tuple) else 0,
        "photos": [str(x) for x in cond.get("photo_refs") or []], "quote": amount, "currency": quote.get("currency") or "USD",
    }  # fmt: skip


def _table(s: Session, case: Mapping[str, Any]) -> tuple[tables_repo.TableRow, str] | None:
    """The approved payout table in force today (the org's own version first) and its label ("US payout rules v1")."""
    spec = tables.market_spec(PACK)
    if spec is None or not spec.has(TABLE):
        return None
    tables_repo.ensure_seeded(s, PACK)
    market = next(iter(spec.markets))
    row = tables_repo.effective(s, case.get("owner"), PACK, spec.flow, market, TABLE, clock.now().date())
    return (row, str(tables.TableRef(PACK, spec.flow, market, TABLE, row.version))) if row else None


def assess_case(s: Session, case: MutableMapping[str, Any], pack: Pack) -> None:
    """Value the payout of a received device once, when its facts are in (module docstring); a case that already has a payout,
    is not a received device or has no facts yet is left alone. In the caller's transaction."""
    if case.get("payout") or _lot(case) is None or (facts := facts_of(s, case)) is None or (found := _table(s, case)) is None:
        return
    row, label = found
    inputs = {k: facts[k] for k in ("declared_grade", "actual_grade", "battery_pct", "functional_fails")}
    limit = max_auto_gap(pack)
    got = assess_payout({"amount": facts["quote"]}, evaluate(row, inputs).outputs, max_auto_gap=limit, cites=(label,))
    rec: dict[str, Any] = {
        "status": "adjusted" if got.auto else "waiting", "quote": float(got.quote), "adjusted": float(got.adjusted),
        "gap_pct": float(got.gap_pct), "reason": got.reason, "table": label, "cites": list(got.cites), "auto": got.auto,
        "limit": float(limit),
        "currency": facts["currency"], "photos": facts["photos"], "inputs": inputs, "prepared_by": "system",
        "at": clock.now().isoformat(), "item": None, "decided": None,
    }  # fmt: skip
    case["payout"] = rec
    if got.auto:
        _journal(s, case, adjusted_line(rec))
        send(s, case)
        return
    rec["item"] = _open_item(s, case, pack, rec, waiting_line(rec, limit))
    _journal(s, case, waiting_line(rec, limit))


def _open_item(s: Session, case: Mapping[str, Any], pack: Pack, rec: Mapping[str, Any], line: str) -> int:
    kind = next((t for t in pack.runtime.exception_types if t.id == EXCEPTION), None)
    cid = str(case["id"])
    photos = ", ".join(rec["photos"]) or "none"
    return process.open_item(
        s, kind="exception", case_id=cid, org_unit_id=case.get("owner"), type=EXCEPTION, title=f"{cid}: {line}",
        cause=f"{line}. Grading photos: {photos}. Graded {rec['inputs']['actual_grade']}, "
        f"declared {rec['inputs']['declared_grade']}.",
        action=f"{OWNER_LABEL}: " + (kind.action if kind else "Decide the payout from the grading photos"),
        owner_role=kind.owner_role if kind else "Planner", due_hours=pack.runtime.sla_hours.get("exception"), by="system",
    )  # fmt: skip


def _journal(s: Session, case: MutableMapping[str, Any], line: str, by: str = "system") -> None:
    """A line in the case's stage log (the journal the case page shows). A case not stored yet keeps it for `flush`."""
    exists = s.execute(text("SELECT 1 FROM case_record WHERE id = :c"), {"c": case["id"]}).first()
    if exists is None:
        case["payout"].setdefault("pending_log", []).append({"line": line, "by": by})
        return
    stage = str(case.get("stage") or "none")
    s.execute(
        text("INSERT INTO case_stage_log (case_id, from_stage, to_stage, reason, actor) VALUES (:c, :st, :st, :r, :a)"),
        {"c": case["id"], "st": stage, "r": line, "a": by},
    )


def flush(s: Session, case: dict[str, Any]) -> None:
    """Write the journal lines a payout assessed before its case was stored kept back (called once the case row exists)."""
    rec = case.get("payout")
    pending = (rec or {}).pop("pending_log", [])
    for e in pending:
        _journal(s, case, e["line"], e["by"])
    if pending:
        store.save(s, case)


def send(s: Session, case: Mapping[str, Any]) -> int | None:
    """Queue the `payout` instruction for the amount now on the case (only when sending instructions is switched on): one row
    and one `instruction.send` job, idempotent on the case and the amount in cents. The step is not part of an approval's plan,
    so its reference is the case's own."""
    from di.services.instructions import queue  # the queue imports the execution layer

    if not queue.enabled():
        return None
    p = case["payout"]
    cents = int((Decimal(str(p["adjusted"])) * 100).to_integral_value())
    ref, key = f"PAYOUT-{case['id']}", f"PAYOUT.{case['id']}.{cents}"
    s.execute(text("DELETE FROM instruction WHERE approval_ref = :r AND step = 0"), {"r": ref})
    iid = s.execute(
        text(
            "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, queued_at) "
            "VALUES (:c, :r, 0, :k, :sys, :key, CAST(:refs AS jsonb), :at) ON CONFLICT (idem_key) DO NOTHING RETURNING id"
        ),
        {"c": case["id"], "r": ref, "k": KIND, "sys": queue.SYSTEM_OF[KIND], "key": key, "refs": f'["{key}"]', "at": clock.now()},
    ).scalar()
    if iid is not None:
        jobs.enqueue(s, "instruction.send", {"instruction_id": iid})
    return int(iid) if iid is not None else None


def decided(s: Session, case: MutableMapping[str, Any], amount: float, reason: str, by: str, at: str) -> None:
    """Record a person's decision on a waiting payout: the amount and reason stand, the item closes, the line goes in the journal
    and the instruction is sent. The caller (`payout.decide`) has checked the status, the amount and who may decide."""
    p = case["payout"]
    quote = Decimal(str(p["quote"]))
    p |= {
        "status": "decided", "adjusted": float(amount),
        "gap_pct": float(((Decimal(str(amount)) - quote) / quote).quantize(Decimal("0.0001"))),
        "decided": {"by": by, "amount": float(amount), "reason": reason, "at": at},
    }  # fmt: skip
    if p.get("item") is not None:
        process.close_item(s, int(p["item"]), f"Payout decided: {money(amount)}", by)
    _journal(s, case, f"Payout decided by {by}: {money(amount)} (quote {money(quote)}): {reason}", by)
    send(s, case)


def view(s: Session, case: Mapping[str, Any]) -> dict[str, Any] | None:  # noqa: ARG001 - the case screens pass their session
    """The case page's `payout` (camel case), or None while there is none (or for a bulk lot)."""
    p = case.get("payout")
    if not isinstance(p, dict) or _lot(case) is None:
        return None
    d = p.get("decided")
    return {
        "status": p["status"], "quote": p["quote"], "adjusted": p["adjusted"], "gapPct": p["gap_pct"], "reason": p["reason"],
        "table": p["table"], "auto": p["auto"], "limit": p.get("limit", 0.1), "currency": p.get("currency") or "USD",
        "photos": list(p.get("photos") or []),
        "item": p.get("item"),
        "decided": {"by": d["by"], "reason": d["reason"], "at": d["at"]} if isinstance(d, dict) else None,
    }  # fmt: skip
