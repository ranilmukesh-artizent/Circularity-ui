"""What the options valuer decides a ticket on (plan 9, P9-4.6, story SD-04; reads I-15 tables, P9-4.1 stock and offers).

    gather(s, case, as_of) -> ServiceDeskInputs | None   the snapshot `modeler.valuers.service_desk.decide_ticket` reads

Per line: the estimate the case holds (P9-4.4), the outputs of the `cover_terms` and `credit_rules` tables with the version each
cites, the `terms` card, the refurbished stock of the class and the median turnaround of the similar repairs. For the case: the
take-up curve (the pack's prior, `{a, b}`; the active `take_up` model of P9-4.11 takes its place, `source` "model <id>"),
the account shift, the fx rate to USD and the approved table versions of the decision date,
which GR-S3 compares each cited version with. Per line
`recall` is the reason GR-12 gives when a notice holds the tool (None otherwise).

- **Account shift.** With at least 10 offers to the account in the 24 months before `as_of`,
  `shift = logit((k + 1) / (n + 2)) - logit(base)`: `k` accepted of `n`, `base` the market's acceptance share in the window.
- **Reads facts dated before `as_of`** only (offers offered before it; tables effective on it; repairs closed before it).
- A market without the five tables returns None: the case is then valued as a plain tool-fleet return, as before.

Never does: write, evaluate a language model, or approve anything.
"""

import math
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from statistics import median
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import market_tables as tables_repo
from di.repositories import model_versions, refurb_stock, rollouts
from di.repositories.repair_history import similar
from di.repositories.upgrade_offers import offers
from di.services.cases import recall_evidence
from di.services.modeler.pack import load_pack
from di.services.modeler.tables import JdmTable, TableRef, ZenEvaluator
from di.services.modeler.valuers import fleet_evidence
from di.services.modeler.valuers.tool_fleet import CLS
from di.services.models.cost import FLOW, PACK

ServiceDeskInputs = dict[str, Any]
CARDS = ("labour", "parts", "terms", "cover_terms", "credit_rules")
MIN_OFFERS = 10
WINDOW_MONTHS = 24


def _ref(row: Any) -> str:
    return str(TableRef(PACK, FLOW, row.market, row.name, row.version))


def _label(market: str, read: str, arm: str) -> str | None:
    """How the case page names the tables a ticket was priced from, outside a normal market: the pilot's new tables, or the
    standard quote (a control ticket, or a new ticket while the pilot is paused or rolled back)."""
    if arm == "canary":
        return f"Pilot {market} (new tables)"
    return "Standard quote" if arm == "control" or read != market else None


def _logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def _since(as_of: date, months: int) -> date:
    y, m = divmod(as_of.year * 12 + as_of.month - 1 - months, 12)
    return date(y, m + 1, min(as_of.day, 28))


def fx_per_usd(s: Session, currency: str, as_of: date) -> Decimal:
    """Units of `currency` per USD on `as_of`: the newest dated rate, else the pack's fixed fallback."""
    if currency == "USD":
        return Decimal(1)
    r = s.execute(
        text("SELECT usd_rate FROM fx_rate WHERE currency = :c AND date <= :d ORDER BY date DESC LIMIT 1"),
        {"c": currency, "d": as_of},
    ).scalar()
    if r is not None:
        return Decimal(str(r))
    return Decimal(str(load_pack(PACK).valuer.params["service_desk"]["options"]["fx_fallback"][currency]))


def account_shift(s: Session, org: str | None, account: str | None, market: str, as_of: date) -> float:
    """The account's lean towards accepting an upgrade against the market's (module docstring); 0 below 10 offers."""
    if not account:
        return 0.0
    since = _since(as_of, WINDOW_MONTHS)
    mine = offers(s, org, account, market, since, as_of)
    if len(mine) < MIN_OFFERS:
        return 0.0
    allm = offers(s, org, None, market, since, as_of)
    base = sum(1 for o in allm if o.accepted) / len(allm)
    k, n = sum(1 for o in mine if o.accepted), len(mine)
    return _logit((k + 1) / (n + 2)) - _logit(base)


def take_up_prior() -> dict[str, float]:
    """The pack's take-up curve `{a, b}`, used until a learned model is promoted."""
    return dict(load_pack(PACK).valuer.params["service_desk"]["options"]["take_up_prior"])


def take_up_of(s: Session, shift: float, market: str) -> dict[str, Any]:
    """The take-up curve of a ticket: the active `take_up` model (P9-4.11; of this market, or fitted on all) with source
    `model <id>`, else the pack's prior with source `prior`."""
    act = model_versions.active(s, "tool_fleet", "take_up")
    if act is not None and act.factors and (act.metrics or {}).get("market") in (None, market):
        return {"a": act.factors[0]["a"], "b": act.factors[0]["b"], "shift": shift, "source": f"model {act.id}"}
    prior = take_up_prior()
    return {"a": prior["a"], "b": prior["b"], "shift": shift, "source": "prior"}


def _decide(row: Any, given: Mapping[str, Any]) -> dict[str, Any]:
    return dict(ZenEvaluator().evaluate(JdmTable.model_validate(row.body), given).outputs)


def stale_refs(s: Session, case: Mapping[str, Any], on: date) -> list[str]:
    """GR-S3: the table versions the case's lines cite that are not the approved versions in force on `on`; empty for a case
    that cites none (not a ticket, or no options yet)."""
    sd = case.get("serviceDesk")
    inputs = sd.get("inputs") if isinstance(sd, dict) else None
    if not inputs:
        return []
    org, market = case.get("owner"), str(inputs["market"])
    rows = (tables_repo.effective(s, org, PACK, FLOW, market, n, on) for n in CARDS)
    now = {_ref(r) for r in rows if r is not None}
    return sorted({c for ln in inputs["lines"] for c in ln.get("cited") or []} - now)


def gather(s: Session, case: Mapping[str, Any], as_of: date, decided_on: date | None = None) -> ServiceDeskInputs | None:
    """The valuer's inputs for the case's ticket on `as_of` (module docstring); None when the market lacks a table. The prices
    are those in force on `as_of` (the estimate's day); `approved` are the versions in force on `decided_on` (default `as_of`,
    never earlier), which GR-S3 compares the cited ones with."""
    base = case.get("serviceDesk")
    if not isinstance(base, dict) or not base.get("market"):
        return None
    org, market = case.get("owner"), str(base["market"])
    tables_repo.ensure_seeded(s, PACK)
    read, arm = rollouts.table_version_for(s, case)  # the market whose tables price the ticket (P9-7.7: a table canary)
    rows = {n: tables_repo.effective(s, org, PACK, FLOW, read, n, as_of) for n in CARDS}
    if any(r is None for r in rows.values()):
        return None
    now = max(decided_on or as_of, as_of)
    current = rows if now == as_of else {n: tables_repo.effective(s, org, PACK, FLOW, market, n, now) for n in CARDS}
    notices = recall_evidence.evidence(s, None, None)["value"]["recalls"]  # GR-12, read once for every line
    own = case.get("recallRelease") if isinstance(case.get("recallRelease"), dict) else None
    cur = rows["labour"].currency or ""  # type: ignore[union-attr]
    terms = {k: float(v) for k, v in rows["terms"].body["values"].items()}  # type: ignore[union-attr]
    history: dict[tuple[str, str], int | None] = {}
    lines = []
    for ln in base["lines"]:
        cls, fault = str(ln["model_class"]), ln.get("fault_code") or None
        cover = _decide(
            rows["cover_terms"],
            {
                "market": market,
                "family": cls,
                "cover_type": ln.get("cover_type") or "none",
                "age_months": ln.get("age_months") or 0,
            },
        )
        credit = _decide(
            rows["credit_rules"],
            {"market": market, "family": cls, "age_months": ln.get("age_months") or 0, "life_used_pct": ln["life_used_pct"]},
        )
        est = ln.get("estimate")
        recall, _, _ = fleet_evidence.recall_check(
            str(ln["serial"]), cls, notices, own if ln["serial"] == case.get("serial") else None
        )  # a person's release frees the line it was given for, as the page's line checks read it
        if fault is not None and (cls, fault) not in history:
            days = [
                r.turnaround_days
                for r in similar(s, org, cls, fault, None, _since(as_of, 36), as_of)
                if r.turnaround_days is not None
            ]
            history[(cls, fault)] = int(median(days)) if days else None
        refs = [_ref(rows[n]) for n in ("terms", "cover_terms", "credit_rules")]
        lines.append(
            {
                "n": ln["n"],
                "serial": ln["serial"],
                "model_class": cls,
                "family": CLS.get(cls, {}).get("name", cls),
                "life_used_pct": ln["life_used_pct"],
                "estimate": est,
                "cover": {
                    "repair_covered": bool(cover["repair_covered"]),
                    "swap_allowed": bool(cover["swap_allowed"]),
                    "upgrade_allowed": bool(cover["upgrade_allowed"]),
                    "reason": str(cover["reason"]),
                    "ref": refs[1],
                },
                "credit": {"credit_pct": float(credit["credit_pct"]), "credit_cap": float(credit["credit_cap"]), "ref": refs[2]},
                "terms": {**terms, "ref": refs[0]},
                "refurb_stock": refurb_stock.available(s, org, cls),
                "fix_days": history.get((cls, fault)) if fault else None,
                "recall": None if recall.passed else recall.reason,  # GR-12: why no option of this tool may run
                "cited": sorted({*(e["cites"] for e in (est or {}).get("lines", [])), *refs}),
            }
        )
    return {
        "market": market,
        "currency": cur,
        "fx": float(fx_per_usd(s, cur, as_of)),
        "as_of": as_of.isoformat(),
        "take_up": take_up_of(s, account_shift(s, org, base.get("account"), market, as_of), market),
        "approved": sorted(_ref(r) for r in current.values() if r is not None),
        "tables": {"market": read, "arm": arm, "label": _label(market, read, arm)},
        "lines": lines,
    }
