"""Cross-region transfer alert and suggestions for telecom spares (plan 9, P9-10.15, story TN-18).

    alerts(units, reqs, idle_days_gt, role, action) -> [Alert]   pure: the idle units and the open requisitions -> the alerts
    alerts_for(s, orgs, pack)                       -> [Alert]   the same over the canonical store (spares planning's records)
    rule_suggestion(pack)                           -> dict|None the pack's `SR-TN-XREGION` as a draft rule {id, text, rule}

`AL-TN-XREGION` (pack `runtime.suggestion_rules`, param `idle_days_gt`, owner `spares_planner`): units of one model idle more
than `idle_days_gt` days in a region (`asset.idle_days`, the spares pool) while ANOTHER region has an open requisition for the
model (`demand.requisitions`, status "open"). One alert per (model, idle region, requisition) for the role the pack's owner
maps to (Planner): "<n> idle <model> in <region>; <other region> raised <req>", action "Transfer to the region buying new",
and one transfer suggestion per unit, oldest idle first, at most the requisition's quantity. `SR-TN-XREGION` ("offer surplus
across regions before a new purchase order") is offered as a draft rule `prefer redeploy`, placed by
`di.services.actions.tn_cross_region` through the rule-suggestion path of `modeler_suggest` (MVP-12.3).
Never does: send or reduce a requisition, move a unit, save or publish a rule, read a clock or call a model; every count
comes from the records. Adopting the rule is the person's own `flow.saveDraft`, then another person's `flow.approve` and
`flow.publish` (maker-checker). Implements the telecom side of registry entry I-4 (rules that run).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical.schema import SHARED_ORG
from di.services.modeler.pack import Pack

ALERT_ID, RULE_ID = "AL-TN-XREGION", "SR-TN-XREGION"


@dataclass(frozen=True)
class Unit:
    serial: str
    model: str
    region: str
    idle_days: int


@dataclass(frozen=True)
class Req:
    req_id: str
    model: str
    region: str
    quantity: int


@dataclass(frozen=True)
class Alert:
    id: str
    to_role: str
    model: str
    region: str
    other_region: str
    req_id: str
    text: str
    action: str
    transfers: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "to_role": self.to_role, "model": self.model, "region": self.region,
            "other_region": self.other_region, "req_id": self.req_id, "text": self.text, "action": self.action,
            "n": len(self.transfers), "transfers": [dict(t) for t in self.transfers],
        }  # fmt: skip


def _rule(pack: Pack, rid: str) -> dict[str, Any]:
    return next((r for r in pack.runtime.suggestion_rules if r.get("id") == rid), {})


def alerts(units: Iterable[Unit], reqs: Iterable[Req], idle_days_gt: int, role: str, action: str) -> list[Alert]:
    """The alerts, ordered by model, requisition, region. A unit idle in the region that raised the requisition is no surplus."""
    idle = [u for u in units if u.idle_days > idle_days_gt]
    out: list[Alert] = []
    for req in sorted(reqs, key=lambda r: (r.model, r.region, r.req_id)):
        here = sorted((u for u in idle if u.model == req.model and u.region != req.region), key=lambda u: (-u.idle_days, u.serial))
        for region in sorted({u.region for u in here}):
            mine = [u for u in here if u.region == region]
            pool = mine[: max(0, req.quantity)]
            if not pool:
                continue
            out.append(
                Alert(
                    ALERT_ID, role, req.model, region, req.region, req.req_id,
                    f"{len(mine)} idle {req.model} in {region}; {req.region} raised {req.req_id}", action,
                    tuple({"serial": u.serial, "model": u.model, "from": region, "to": req.region, "req_id": req.req_id,
                           "idle_days": u.idle_days} for u in pool),
                )
            )  # fmt: skip
    return out


def _org_match(key: str, orgs: Sequence[str]) -> bool:
    return key.partition(":")[0] in (*orgs, SHARED_ORG)


def read(s: Session, orgs: Sequence[str]) -> tuple[list[Unit], list[Req]]:
    """The spares pool's idle units and the open requisitions of the org units (and `shared`) from the canonical store."""
    units: list[Unit] = []
    for key, d in s.execute(text("SELECT key, data FROM canonical WHERE model = 'asset' AND data ? 'idle_days'")):
        model = d.get("part_number") or d.get("model")
        if _org_match(key, orgs) and d.get("region") and model:
            units.append(Unit(str(d.get("serial") or key.partition(":")[2]), str(model), str(d["region"]), int(float(d["idle_days"]))))
    reqs: list[Req] = []
    for key, d in s.execute(text("SELECT key, data FROM canonical WHERE model = 'demand' AND data ? 'requisitions'")):
        if not _org_match(key, orgs):
            continue
        _org, region, model = key.split(":", 2)
        for r in d.get("requisitions") or []:
            if isinstance(r, Mapping) and str(r.get("status")).lower() == "open":
                reqs.append(Req(str(r["reqId"]), model, region, int(float(r.get("quantity") or 0))))
    return units, reqs


def alerts_for(s: Session, orgs: Sequence[str], pack: Pack) -> list[Alert]:
    al = _rule(pack, ALERT_ID)
    units, reqs = read(s, orgs)
    role = pack.roles.get(str(al.get("owner")), "Planner")
    days = int((al.get("params") or {}).get("idle_days_gt", 30))
    return alerts(units, reqs, days, role, str(al.get("action") or "Transfer to the region buying new"))


def rule_suggestion(pack: Pack) -> dict[str, Any] | None:
    """`SR-TN-XREGION` as a draft rule: prefer the redeploy route (the unit fills a need) over a new purchase."""
    sr = _rule(pack, RULE_ID)
    if not sr:
        return None
    label = str(sr["label"])
    return {"id": RULE_ID, "text": label[:1].upper() + label[1:], "rule": {"action": "prefer", "path": "redeploy", "scope": {}}}
