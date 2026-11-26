"""The money facts of a telecom unit, read from the canonical store for the telecom valuer (plan 9, P9-10.11; entry I-21).

    gather(s, case) -> {"asset", "condition", "market", "demand", "spares"}   the unit's canonical records and the facts derived
                                                                              from them, as nested dicts (a group with nothing
                                                                              is absent; an unknown unit gives {})
    overlay(s, case) -> case                                                  the case with those facts laid in its `valuer`
                                                                              wherever the case does not already hold them

The adapters of the network inventory, the test bench, spares planning, the broker marketplace and the decommission tracker write
these records (P9-10.2 to P9-10.5); until now a case kept only the facts it was opened with, so a stored unit had no market,
no demand and no spares gap and every route read "not valued: input missing". `decide_case` calls `overlay` on every decision
(when it has a session), so a re-evaluation values the unit on the market as it is now. What a case already holds wins (a sample,
a replay, a simulation, a person's override): the store only fills the gaps.

What is read, and where it lands (keys carry the unit's org unit, `shared` when it has none):
    asset.<serial key>, condition.<serial key>   asset.*, condition.* whole; `asset.firmware` and `asset.firmware_major_gap`
                                                 from the condition when the inventory has no firmware
    market.<org>:<model>, market.<model>         market.new_price, generation (catalogue); broker_bids, cleared_price (broker)
    demand.<org>:<region>:<model>                demand.use_probability and need_6m as {region: number}
    demand.<demand id> (site_demand)             the open site demand for the unit's model, earliest need-by first:
                                                 demand.open_site_demand, id, site, model, firmware_min_major, region
    asset.<serial key> of a spares pool unit     spares.gap and spares.region_below_target: the region of the model with the
                                                 most units missing (target minus the pool units that hold the model)
Not read: `demand.board_needs` (open repair needs for a board): no connected system serves them, so harvest stays "No open
repair need for a board" until one does.
Never does: write a record, read a clock, or decide anything. A fact the store does not hold is left out, never made up.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical import store as canonical
from di.services.canonical.schema import SHARED_ORG

GROUPS = ("asset", "condition", "market", "demand", "spares")


def _data(s: Session, model: str, key: str) -> dict[str, Any]:
    rec = canonical.get(s, model, key)
    return dict(rec["data"]) if rec and rec.get("data") else {}


def _orgs(asset_key: str) -> list[str]:
    """The org units a key of this unit's sources may carry: its own, then `shared`."""
    org = asset_key.partition(":")[0]
    return [org] if org == SHARED_ORG else [org, SHARED_ORG]


def _model_of(case: Mapping[str, Any], asset: Mapping[str, Any]) -> str | None:
    net = case.get("network") if isinstance(case.get("network"), Mapping) else {}
    v = case.get("valuer") if isinstance(case.get("valuer"), Mapping) else {}
    for m in (asset.get("model"), net.get("model"), v.get("asset.model"), (v.get("asset") or {}).get("model")):  # type: ignore[union-attr]
        if m:
            return str(m)
    return None


def _market(s: Session, orgs: list[str], model: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in [*(f"{o}:{model}" for o in orgs), model]:  # the catalogue by org unit, the broker's by model alone
        for k, v in _data(s, "market", key).items():
            out.setdefault(k, v)
    return out


def _cells(s: Session, orgs: list[str], model: str) -> dict[str, dict[str, Any]]:
    """The spares planning cells of the model by region (the unit's org unit's cell before the shared one)."""
    out: dict[str, dict[str, Any]] = {}
    for org in orgs:
        rows = s.execute(
            text("SELECT key, data FROM canonical WHERE model = 'demand' AND starts_with(key, :p) ORDER BY key"),
            {"p": f"{org}:"},
        ).all()
        for key, data in rows:
            region, _, m = key.removeprefix(f"{org}:").rpartition(":")
            if m == model and region and ":" not in region:
                out.setdefault(region, dict(data))
    return out


def _site_demand(s: Session, model: str) -> dict[str, Any] | None:
    """The open site demand for the model that is needed first (the tracker serves open demands only)."""
    rows = s.execute(
        text(
            "SELECT key, data -> 'site_demand' FROM canonical WHERE model = 'demand' AND data -> 'site_demand' ->> 'model' = :m"
        ),
        {"m": model},
    ).all()
    docs = sorted(
        (dict(d) for _, d in rows if isinstance(d, dict)), key=lambda d: (str(d.get("needBy") or "9999"), str(d.get("demandId")))
    )
    return docs[0] if docs else None


def _pool(s: Session, orgs: list[str], model: str) -> dict[str, int]:
    """The spares pool's units that hold the model, by region (an `asset` with `idle_days` is a pool unit)."""
    out: dict[str, int] = {}
    for org in orgs:
        rows = s.execute(
            text(
                "SELECT data ->> 'region' FROM canonical WHERE model = 'asset' AND starts_with(key, :p) AND data ? 'idle_days' "
                "AND (data ->> 'part_number' = :m OR data ->> 'model' = :m)"
            ),
            {"p": f"{org}:", "m": model},
        ).scalars()
        for region in rows:
            out[str(region)] = out.get(str(region), 0) + 1
    return out


def _spares(cells: Mapping[str, Mapping[str, Any]], pool: Mapping[str, int]) -> dict[str, Any]:
    """The region with the most units missing against its target, and how many (nothing when no region is short)."""
    short = {
        r: int(c["spares_target"]) - pool.get(r, 0) for r, c in cells.items() if isinstance(c.get("spares_target"), int | float)
    }
    short = {r: g for r, g in short.items() if g > 0}
    if not short:
        return {}
    region = min(short, key=lambda r: (-short[r], r))
    return {"gap": short[region], "region_below_target": region}


def gather(s: Session, case: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The unit's facts from the canonical store (module docstring); {} when the store holds no record of the unit."""
    key = str(case.get("assetId") or "")
    if not key:
        return {}
    asset, cond = _data(s, "asset", key), _data(s, "condition", key)
    if not asset and not cond:
        return {}
    orgs = _orgs(key)
    if "firmware" not in asset and cond.get("firmware"):
        asset["firmware"] = cond["firmware"]
    if "firmware_major_gap" not in asset and cond.get("firmware_major_gap") is not None:
        asset["firmware_major_gap"] = cond["firmware_major_gap"]
    out: dict[str, dict[str, Any]] = {"asset": asset, "condition": cond}
    model = _model_of(case, asset)
    demand: dict[str, Any] = {"open_site_demand": False}
    if model:
        out["market"] = _market(s, orgs, model)
        cells = _cells(s, orgs, model)
        for field in ("use_probability", "need_6m"):
            by_region = {r: c[field] for r, c in cells.items() if c.get(field) is not None}
            if by_region:
                demand[field] = by_region
        if site := _site_demand(s, model):
            demand |= {
                "open_site_demand": True, "id": site.get("demandId"), "site": site.get("siteId"), "model": site.get("model"),
                "firmware_min_major": site.get("minFirmwareMajor"), "region": site.get("region"),
            }  # fmt: skip
        out["spares"] = _spares(cells, _pool(s, orgs, model))
    out["demand"] = demand
    return {g: v for g, v in out.items() if v and g in GROUPS}


def _held(case: Mapping[str, Any], valuer: Mapping[str, Any], group: str, name: str) -> bool:
    """The case already has the fact: nested in its own fields or the snapshot, or as a flat dotted key."""
    path = f"{group}.{name}"
    for src in (case, valuer):
        if src.get(path) is not None or (isinstance(src.get(group), Mapping) and src[group].get(name) is not None):
            return True
    return False


def overlay(s: Session, case: Mapping[str, Any]) -> dict[str, Any]:
    """The case with the unit's canonical facts laid in its `valuer`, only where the case holds none (module docstring)."""
    facts = gather(s, case)
    out = dict(case)
    if not facts:
        return out
    valuer = dict(case.get("valuer") or {})
    for group, values in facts.items():
        merged: dict[str, Any] = {}
        for src in (case, valuer):  # `facts_of` lets the snapshot's group replace the case's, so both are carried over
            if isinstance(src.get(group), Mapping):
                merged |= src[group]
        merged |= {k: v for k, v in values.items() if not _held(case, valuer, group, k)}
        valuer[group] = merged
    out["valuer"] = valuer
    return out
