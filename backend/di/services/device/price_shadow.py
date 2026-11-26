"""The shadow of a retrained price model (plan 9, P9-6.18, registry entry I-14 `PriceModel`; story DV-14).

Owns:
- `min_shadow()`: the evaluations a price candidate must be shadowed on before it may be promoted (the device pack's
  `valuer.params.price_shadow.min_shadow`, 30), and `shadow_count` / `block_text`: how many it has, and the refusal's text;
- `stats(s, model_id)`: the count, and the candidate's and the active model's MAE and coverage on the shadowed cases whose
  device has sold (the case's `priceShadow`, written by `di.services.device.inputs.record_price_shadow`, joined to the sale);
- `refit_due` / `refit`: the worker's `device.priceRefit` job, which fits a candidate as the system once 200 sales settled
  since the active model's window.

Never does: propose or promote a model (a person proposes, a different person promotes: `model.propose`, `model.promote`),
let a shadow band reach a case's channel, price or net, or use a language model: every figure is counted or computed (R16).
MAE and coverage grade a device only on a sale settled after its shadow and after the candidate's training window (not in-sample).
A case counts once per candidate (its `priceShadow` is rewritten at every valuation). MAE and coverage are measured only on
cases where both the candidate and the active model have a band for the channel the device sold on, so the two compare on the
same devices, and only on a sale settled after the shadow was taken and after the candidate's training window (never in-sample).
"""

import json
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import device_market
from di.repositories import model_versions as repo
from di.services.modeler.pack import load_pack
from di.services.models import price_rows

REFIT_SALES = 200  # sales settled since the active model's window that make a refit due
DEFAULT_MIN = 30


def min_shadow() -> int:
    """The shadowed evaluations a price candidate needs before promotion (the pack's, 30)."""
    params = load_pack("device").valuer.params.get("price_shadow") or {}
    return int(params.get("min_shadow", DEFAULT_MIN))


def block_text(n: int, minimum: int) -> str:
    return f"A price model is shadowed on {minimum} evaluations before promotion ({n} so far)."


def _shadows(s: Session, model_id: str) -> list[dict[str, Any]]:
    rows = s.execute(
        text("SELECT data -> 'priceShadow' FROM case_record WHERE data -> 'priceShadow' ->> 'model_id' = :m ORDER BY id"),
        {"m": model_id},
    )
    return [r[0] for r in rows]


def shadow_count(s: Session, model_id: str) -> int:
    """The cases that carry the candidate's shadow band."""
    return int(
        s.execute(
            text("SELECT count(*) FROM case_record WHERE data -> 'priceShadow' ->> 'model_id' = :m"), {"m": model_id}
        ).scalar_one()
    )


def _trained_to(s: Session, model_id: str) -> date | None:
    """The last day of the data the candidate was fitted on (its `metrics.window.to`), or None when it names none."""
    row = repo.get(s, model_id)
    to = ((row.metrics if row else None) or {}).get("window", {}).get("to")
    return date.fromisoformat(str(to)[:10]) if to else None


def _sold(s: Session, imei: str, after: date | None = None) -> tuple[float, str] | None:
    """The newest settled sale of the device on a day after `after`: its price and channel (the listing's, `wholesale` for a lot,
    else `other`). A sale on or before `after` is not counted: the candidate was shadowed or trained on it."""
    row = s.execute(
        text(
            "SELECT sale_id FROM device_sale WHERE imeis @> CAST(:j AS jsonb) "
            "AND (CAST(:a AS date) IS NULL OR settled_at >= CAST(:a AS date) + 1) ORDER BY settled_at DESC, sale_id DESC LIMIT 1"
        ),
        {"j": json.dumps([imei]), "a": after},
    ).first()
    if row is None:
        return None
    sale = device_market.sales_by_id(s, [row[0]])[0]
    return sale.price, price_rows.sale_channel(s, sale)


def _inside(b: dict[str, float], y: float) -> bool:
    return b["p10"] <= y <= b["p90"]


def stats(s: Session, model_id: str) -> dict[str, Any]:
    """`{n, min, settled, mae, coverage, mae_active, coverage_active}` of the candidate's shadow; the figures are None until a
    shadowed device has sold."""
    shadows = _shadows(s, model_id)
    cand: list[tuple[float, bool]] = []
    act: list[tuple[float, bool]] = []
    trained = _trained_to(s, model_id)
    for sh in shadows:
        # graded only on a sale settled after the shadow was taken and after the training window (never in-sample)
        taken = date.fromisoformat(str(sh["at"])[:10]) if sh.get("at") else None
        after = max((d for d in (taken, trained) if d is not None), default=None)
        sold = _sold(s, str(sh.get("imei") or ""), after) if sh.get("imei") else None
        if sold is None:
            continue
        y, channel = sold
        c = (sh.get("bands") or {}).get(channel)
        a = ((sh.get("active") or {}).get("bands") or {}).get(channel)
        if c is None or a is None:
            continue
        cand.append((abs(c["p50"] - y), _inside(c, y)))
        act.append((abs(a["p50"] - y), _inside(a, y)))

    def mean(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    return {
        "n": len(shadows), "min": min_shadow(), "settled": len(cand),
        "mae": mean([e for e, _ in cand]), "mae_active": mean([e for e, _ in act]),
        "coverage": mean([1.0 if i else 0.0 for _, i in cand]), "coverage_active": mean([1.0 if i else 0.0 for _, i in act]),
    }  # fmt: skip


# ---------------------------------------------------------------- the refit job
def refit_due(s: Session, today: date) -> bool:
    """True when no price candidate waits and `REFIT_SALES` sales settled after the active model's window (all sales when no
    model is active)."""
    if repo.candidate(s, "device", "price") is not None:
        return False
    act = repo.active(s, "device", "price")
    window = ((act.metrics if act else None) or {}).get("window") or {}
    since = date.fromisoformat(str(window["to"])) if window.get("to") else None
    n = s.execute(
        text(
            "SELECT count(*) FROM device_sale WHERE settled_at < CAST(:t AS date) + 1 "
            "AND (CAST(:w AS date) IS NULL OR settled_at >= CAST(:w AS date) + 1)"
        ),
        {"t": today, "w": since},
    ).scalar_one()
    return int(n) >= REFIT_SALES


def refit(s: Session, today: date) -> str | None:
    """Fit a candidate through `model.fit` as the system when a refit is due; its id, else None. Never proposes or promotes."""
    if not refit_due(s, today):
        return None
    from di.services.actions.pipeline import SYSTEM, CallContext, invoke  # lazily: the pipeline imports the devices

    r = invoke("model.fit", {"template": "device", "kind": "price"}, CallContext(actor=SYSTEM, session=s))
    return str(r["output"]["id"]) if r.get("ok") else None
