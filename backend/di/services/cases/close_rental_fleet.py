"""The close of a rental fleet machine: damage recovery from the renter, and the cross-branch transfer alert (plan 9, P9-12.5;
stories NS-RC-02 and NS-RC-03; reads registry entries I-7 (the outcome stage) and I-10 (the hold policy)).

    close_case(s, case_id, ctx=None) -> CloseResult   what the close prepares for an approved machine's damage claims
    rentalFleet.chargeDamage  {case_id, claim_id, renter_ref, amount, photos_ref}   the customer charge, recorded once Finance accepts
    alerts(machines, idle_days_gt, role, action) -> [Alert]   pure: idle machines and other branches' purchase plans -> alerts
    alerts_for(s, orgs, pack) -> [Alert]                      the same over the canonical store (rental system's records)
    rule_suggestion(pack) -> dict | None                      the pack's `SR-RF-XBRANCH` as a draft rule {id, text, rule}

Damage recovery. The rental system's check-in damage claims of the machine (canonical `condition.damage_claims`, else the case's
own facts) are read at close. Each claim of at least the pack's `close.damage_charge_min` becomes an agent-prepared
`rentalFleet.chargeDamage` with the renter reference, the amount and the photos reference. The action is in HELD_FOR_PERSON, so
the hold policy holds it as a proposal for Finance at every autonomy level (`proposal.accept` is a person's, never an agent's).
Accepting it records the charge on the case (`close.posted["damage_charge:<claim>"]`). A second close prepares nothing new for a
claim that already has a proposal, whatever its state. The charge is never sent by an agent, and no instruction row is queued: the
ERP posting of a customer charge has no writer yet (decision of P9-12.5).

`AL-RF-XBRANCH` (pack `runtime.suggestion_rules`, param `idle_days_gt`, owner `branch_manager`): a machine idle more than
`idle_days_gt` days at one branch while ANOTHER branch plans to buy its class (`demand.purchase_plans`, the other branches' plans
the adapter keeps) gives one alert per (idle branch, class, buying branch) for the role the owner maps to: "<n> idle <class> at
<branch>; <other> plans to buy", action "Transfer to the branch buying new", and one `transfer_branch` suggestion per machine,
oldest idle first, at most the plan's quantity. `SR-RF-XBRANCH` is offered as a draft rule `prefer transfer_branch`, as
`tn_cross_region` does for telecom (adopting it is a person's own `flow.saveDraft`, then maker-checker).

Never does: send a charge, approve anything, move a machine, change a plan, save a rule, read a clock or call a model (R16: this
reads facts and compares). Legal note: charging a renter for damage needs review by Kinective's Legal team before it is relied on.
"""

# ruff: noqa: E501 - long sentence and SQL lines

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import clock
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.canonical import store as canonical
from di.services.canonical.schema import SHARED_ORG
from di.services.cases import store as case_store
from di.services.modeler.pack import Pack, load_pack

TEMPLATE = "rental_fleet"
ACTION = "rentalFleet.chargeDamage"
AGENT = "coordinator"  # the agent that prepares the charge when the caller is not one (a person's call, a test)
ALERT_ID, RULE_ID = "AL-RF-XBRANCH", "SR-RF-XBRANCH"
CENT = Decimal("0.01")

Status = Literal["closed", "not_applicable", "not_approved"]


@dataclass(frozen=True)
class CloseResult:
    status: Status
    reason: str = ""
    posts: list[dict[str, Any]] = field(default_factory=list)


def _money(v: Any) -> float:
    return float(Decimal(str(v)).quantize(CENT, ROUND_HALF_UP))


def _claims(s: Session, c: case_store.Case) -> list[dict[str, Any]]:
    """The machine's damage claims: the rental system's record, else the facts the case was opened with."""
    rec = (canonical.get(s, "condition", str(c.get("assetId") or "")) or {}).get("data") or {}
    claims = rec.get("damage_claims")
    if claims is None:
        claims = ((c.get("valuer") or {}).get("condition") or {}).get("damage_claims")
    return [dict(x) for x in claims or [] if isinstance(x, Mapping) and x.get("claimId")]


def _prepared(s: Session, case_id: str, claim_id: str) -> int | None:
    """The id of a charge proposal already prepared for this claim (any state: a rejected one is not asked again)."""
    row = s.execute(
        text(
            "SELECT id FROM agent_proposal WHERE action = :a AND case_id = :c AND input ->> 'claim_id' = :k ORDER BY id DESC LIMIT 1"
        ),
        {"a": ACTION, "c": case_id, "k": claim_id},
    ).scalar()
    return int(row) if row is not None else None


def _agent_ctx(s: Session, ctx: CallContext | None) -> CallContext:
    if ctx is None:
        return CallContext(actor=SYSTEM, session=s, preparer=AGENT)
    return replace(ctx, session=s, preparer=ctx.preparer or AGENT, confirmed=False)


def _charge(s: Session, c: case_store.Case, claim: Mapping[str, Any], ctx: CallContext | None) -> dict[str, Any]:
    body = {
        "case_id": c["id"], "claim_id": str(claim["claimId"]), "renter_ref": str(claim.get("renterRef") or ""),
        "amount": _money(claim["amount"]), "photos_ref": str(claim.get("photosRef") or ""),
    }  # fmt: skip
    post = {"kind": "damage_charge", "claim_id": body["claim_id"], "amount": body["amount"], "renter_ref": body["renter_ref"]}
    if (pid := _prepared(s, c["id"], body["claim_id"])) is not None:
        return post | {"state": "exists", "proposal": pid}
    r = invoke(ACTION, body, _agent_ctx(s, ctx))
    if r["ok"] and isinstance(r["output"], dict) and "held" in r["output"]:
        return post | {"state": "held", "proposal": r["output"]["held"]}
    return post | {"state": "refused", "why": r["error"]["message"] if not r["ok"] else "Not held for a person."}


def close_case(s: Session, case_id: str, ctx: CallContext | None = None) -> CloseResult:
    """Record the close of an approved rental fleet machine and prepare a held charge for each damage claim of at least the
    pack's `close.damage_charge_min` (module docstring)."""
    c = case_store.get(s, case_id, for_update=True)
    if c is None or c.get("template") != TEMPLATE:
        return CloseResult("not_applicable", "Not a rental fleet case.")
    route = c.get("chosen")
    if not c.get("exec") or not route:
        return CloseResult("not_approved", "No decision has been approved for the machine yet.")
    minimum = load_pack(TEMPLATE).close.damage_charge_min
    posts: list[dict[str, Any]] = []
    if minimum is not None:
        for claim in _claims(s, c):
            if Decimal(str(claim.get("amount") or 0)) >= Decimal(str(minimum)):
                posts.append(_charge(s, c, claim, ctx))
    close = dict(c.get("close") or {})
    close |= {"route": str(route.get("id") or "").split(":", 1)[0], "at": (ctx.now if ctx else clock.now()).isoformat()}
    close["damage_claims"] = len(_claims(s, c))
    c["close"] = close
    case_store.save(s, c)
    return CloseResult("closed", "The outcome is recorded.", posts)


# ---------------------------------------------------------------- the action
ACTIONS.setdefault(
    ACTION,
    ActionDef(
        id=ACTION, title="Charge a renter for damage", verb="charge a renter for check-in damage",
        desc="Record the customer charge for a machine's check-in damage claim once Finance accepts it. An agent's call is held "
        "for a person.",
        risk="act", perm="confirm", scope="case",
        input={
            "case_id": {"req": True, "t": "string"},
            "claim_id": {"req": True, "t": "string"},
            "renter_ref": {"req": True, "t": "string"},
            "amount": {"req": True, "t": "number"},
            "photos_ref": {"req": False, "t": "string"},
        },
    ),
)  # fmt: skip


def _fleet_case(ctx: CallContext, case_id: str) -> case_store.Case | None:
    c = case_store.get(ctx.session, case_id)
    return c if c is not None and c.get("template") == TEMPLATE else None


@guard(ACTION)
def charge_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    c = _fleet_case(ctx, i["case_id"])
    if c is None:
        return "not_found", f"No live rental fleet case {i['case_id']}."
    if not i["amount"] or i["amount"] < 0:
        return "validation_error", "The amount is zero or negative."
    if f"damage_charge:{i['claim_id']}" in ((c.get("close") or {}).get("posted") or {}):
        return "duplicate", f"The charge for claim {i['claim_id']} is already recorded."
    return None


@implement(ACTION, idem=lambda i, ctx: f"{i['case_id']}:damage_charge:{i['claim_id']}")  # noqa: ARG005 - the key is the input
def charge(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = case_store.get(ctx.session, i["case_id"], for_update=True)
    if c is None:  # not reached: the guard found it
        raise ActionError("not_found", f"No live rental fleet case {i['case_id']}.")
    rec = {
        "claim_id": i["claim_id"], "renter_ref": i["renter_ref"], "amount": _money(i["amount"]),
        "photos_ref": i.get("photos_ref") or "", "by": ctx.actor.id, "at": ctx.now.isoformat(),
    }  # fmt: skip
    close = dict(c.get("close") or {})
    close["posted"] = {**(close.get("posted") or {}), f"damage_charge:{i['claim_id']}": rec}
    c["close"] = close
    case_store.save(ctx.session, c)
    return {"case_id": c["id"], "kind": "damage_charge"} | rec


# ---------------------------------------------------------------- the cross-branch transfer alert
@dataclass(frozen=True)
class Machine:
    machine_id: str
    cls: str
    branch: str
    idle_days: int
    plans: tuple[tuple[str, str, int], ...] = ()  # (branch, class, qty) of the other branches' purchase plans


@dataclass(frozen=True)
class Alert:
    id: str
    to_role: str
    cls: str
    branch: str
    to_branch: str
    text: str
    action: str
    transfers: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "to_role": self.to_role, "class": self.cls, "branch": self.branch, "to_branch": self.to_branch,
            "text": self.text, "action": self.action, "n": len(self.transfers), "transfers": [dict(t) for t in self.transfers],
        }  # fmt: skip


def alerts(machines: Iterable[Machine], idle_days_gt: int, role: str, action: str) -> list[Alert]:
    """The alerts, ordered by class, idle branch, buying branch. A plan at the machine's own branch is no reason to move it."""
    idle = [m for m in machines if m.idle_days > idle_days_gt]
    wants: dict[tuple[str, str], int] = {}  # (class, buying branch) -> quantity planned
    for m in idle:
        for branch, cls, qty in m.plans:
            if cls == m.cls and branch != m.branch:
                wants.setdefault((cls, branch), qty)
    out: list[Alert] = []
    for cls, to_branch in sorted(wants):
        here = sorted((m for m in idle if m.cls == cls and m.branch != to_branch), key=lambda m: (-m.idle_days, m.machine_id))
        for branch in sorted({m.branch for m in here}):
            mine = [m for m in here if m.branch == branch]
            pool = mine[: max(0, wants[(cls, to_branch)])]
            if not pool:
                continue
            out.append(
                Alert(
                    ALERT_ID, role, cls, branch, to_branch, f"{len(mine)} idle {cls} at {branch}; {to_branch} plans to buy", action,
                    tuple({"machine_id": m.machine_id, "route": "transfer_branch", "from": branch, "to": to_branch,
                           "idle_days": m.idle_days} for m in pool),
                )
            )  # fmt: skip
    return out


def _rule(pack: Pack, rid: str) -> dict[str, Any]:
    return next((r for r in pack.runtime.suggestion_rules if r.get("id") == rid), {})


def read(s: Session, orgs: Sequence[str]) -> list[Machine]:
    """The rental system's machines of the org units (and `shared`) with an idle-days reading, from the canonical store."""
    plans = {
        k: d.get("purchase_plans") or []
        for k, d in s.execute(text("SELECT key, data FROM canonical WHERE model = 'demand' AND data ? 'purchase_plans'"))
    }
    out: list[Machine] = []
    for key, d in s.execute(text("SELECT key, data FROM canonical WHERE model = 'asset' AND data ? 'idle_days'")):
        if key.partition(":")[0] not in (*orgs, SHARED_ORG) or not (d.get("branch") and d.get("asset_class")):
            continue
        mine = tuple(
            (str(p["branch"]), str(p["assetClass"]), int(float(p.get("qty") or 0)))
            for p in plans.get(key, [])
            if isinstance(p, Mapping)
        )
        out.append(
            Machine(
                str(d.get("machine_id") or key.partition(":")[2]),
                str(d["asset_class"]),
                str(d["branch"]),
                int(float(d["idle_days"])),
                mine,
            )
        )
    return out


def alerts_for(s: Session, orgs: Sequence[str], pack: Pack) -> list[Alert]:
    al = _rule(pack, ALERT_ID)
    role = pack.roles.get(str(al.get("owner")), "Planner")
    days = int((al.get("params") or {}).get("idle_days_gt", 30))
    return alerts(read(s, orgs), days, role, str(al.get("action") or "Transfer to the branch buying new"))


def rule_suggestion(pack: Pack) -> dict[str, Any] | None:
    """`SR-RF-XBRANCH` as a draft rule: prefer the branch-transfer route over a new purchase."""
    sr = _rule(pack, RULE_ID)
    if not sr:
        return None
    label = str(sr["label"])
    return {
        "id": RULE_ID,
        "text": label[:1].upper() + label[1:],
        "rule": {"action": "prefer", "path": "transfer_branch", "scope": {}},
    }
