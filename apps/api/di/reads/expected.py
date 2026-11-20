"""Expected returns (the demo's EXPECTED): leases and contracts ending soon, completed as the demo completes each entry at
load (contract, lease period, warehouse, likely outcome and its probabilities, the return window and the
probability-weighted planning range). One table, read by the Expected returns screen and the workspace reads.

- `EXPECTED`: every entry, in the demo's shape (the screen sends them as they are).
- `expected_for(account, ctx)`: the entries an account may see: its tenants and, for a Warehouse Manager, its
  warehouse (the demo's whOK).
- `exp_vis(ctx)`: the demo's expVis for the reads (briefing, Actions on me, receiving.plan): the visible entries with
  the window and the probability of a return at the top level, as those reads use them (the adapter from the full
  entry; the short table the reads had before held the same values).
"""

import re

from di import policy
from di.actions.pipeline import CallContext
from di.engine.jsmath import js_round
from di.reads.common import AS_OF, fmt_d, hash_id, iso, ms, to_fixed

_EXPECTED_BASE = [
    ("ER-3101", "Industrial motor", "motor", "Customer A", "12 Oct", "Lease LS-5412 ends 11 Oct", "$3.1k–$8.2k", "Site 3"),
    ("ER-3102", "Hydraulic pump", "pump", "Customer B", "14 Oct", "Lease LS-5440 ends 13 Oct", "$1.4k–$3.6k", "Site 7"),
    ("ER-3103", "Power tool", "drill", "Customer A", "15 Oct", "Site 1 tool-crib refresh", "$90–$240", "Site 1"),
    ("ER-3104", "Tool-fleet batch", "batch", "Customer C", "17 Oct", "Project P-7 closes", "$1.6k–$3.9k", "Site 6"),
    ("ER-3105", "IT electronics", "it", "Customer B", "19 Oct", "Laptop refresh wave 2 (22 units)", "$2.2k–$5.1k", "Site 4"),
    ("ER-3106", "Control unit", "control", "Customer C", "21 Oct", "Line 4 upgrade", "$0.8k–$2.9k", "Site 8"),
    ("ER-3107", "Industrial motor", "motor", "Customer B", "24 Oct", "Lease LS-5471 ends 22 Oct", "$2.6k–$7.4k", "Site 2"),
    ("ER-3108", "Hydraulic pump", "pump", "Customer A", "28 Oct", "Failure-driven swap at Site 5", "$0.9k–$2.8k", "Site 5"),
    ("ER-3109", "Power tool", "drill", "Customer C", "30 Oct", "Warranty return batch", "$60–$180", "Site 6"),
]


def _reason(signal: str) -> str:
    if signal.startswith("Lease"):
        return "Lease ends"
    if re.search("refresh", signal, re.I):
        return "Refresh programme"
    if re.search("swap|Warranty", signal, re.I):
        return "Contract ends (swap or warranty)"
    return "Contract ends"


def _parse_k(s: str) -> int:
    m = re.search(r"\$([\d.]+)(k?)", s or "")
    return js_round(float(m[1]) * (1000 if m[2] else 1)) if m else 0


def _kfmt_e(n: float) -> str:
    return f"${to_fixed(n / 1000, 1)}k" if n >= 1000 else f"${js_round(n)}"


def _utc(y: int, mo: int, d: int) -> int:
    """Date.UTC(y, mo, d) with JavaScript's month and day overflow (mo is 0-based)."""
    y += mo // 12
    mo %= 12
    return ms(f"{y:04d}-{mo + 1:02d}-01") + (d - 1) * 86_400_000


def _expected() -> list[dict]:
    """The demo's EXPECTED, as it completes each entry at load: contract, lease period, warehouse, likely outcome and its
    probabilities, the return window and the probability-weighted planning range."""
    out = []
    first_stage = "Stage 1 · Lease ends"
    for i, (eid, product, cls, owner, date, signal, rng, loc) in enumerate(_EXPECTED_BASE):
        h = int(hash_id(eid), 16)
        lm = re.search(r"LS-\d+", signal)
        months = [24, 36, 36, 48, 24, 36][h % 6]
        day = int(date.split(" ")[0])
        expiry, start = _utc(2026, 9, day - 1), _utc(2026, 9 - months, day)
        pr = [62 + h % 20, 0, 0, 0] if lm else [100, 0, 0, 0]
        if lm:
            rest = 100 - pr[0]
            pr[1] = js_round(rest * 0.45)
            pr[2] = js_round(rest * 0.35)
            pr[3] = rest - pr[1] - pr[2]
        lo, hi = _parse_k(rng.split("–")[0]), _parse_k(rng.split("–")[1])
        stage = first_stage if day - 2 > int(iso(AS_OF)[8:10]) else "Stage 2 · Return authorised"
        out.append(
            {
                "id": eid,
                "product": product,
                "cls": cls,
                "owner": owner,
                "date": date,
                "signal": signal,
                "range": rng,
                "loc": loc,
                "contract": lm[0] if lm else f"CT-{7031 + i * 7}",
                "customer": owner,
                "source": "Contract Management",
                "reason": _reason(signal),
                "expiry": iso(expiry),
                "start": iso(start),
                "lease": {"start": iso(start), "end": iso(expiry), "months": months},
                "wh": ["Warehouse 1", "Warehouse 2"][h % 2],
                "outcome": {
                    "probs": {"Return": pr[0], "Buyout": pr[1], "Extension": pr[2], "Early termination": pr[3]},
                    "likely": "Return",
                    "prob": pr[0],
                    "window": f"{fmt_d(_utc(2026, 9, day - 2))}–{fmt_d(_utc(2026, 9, day + 12))}",
                    "modelled": bool(lm),
                },
                "wRange": f"{_kfmt_e(lo * pr[0] / 100)}–{_kfmt_e(hi * pr[0] / 100)}",
                "run_stage": stage,
            }
        )
    return out


EXPECTED = _expected()


def expected_for(a: policy.Account, pctx: policy.Context | None) -> list[dict]:
    """The expected returns in the account's tenants, and at its warehouse for a Warehouse Manager (the demo's whOK)."""
    wh_scoped = policy.policy(a).get("warehouseScoped")
    return [e for e in EXPECTED if policy.tenant_ok(a, e["owner"], pctx) and (not wh_scoped or e["wh"] == a.warehouse)]


def _brief(e: dict) -> dict:
    return {**e, "window": e["outcome"]["window"], "prob": e["outcome"]["prob"]}


def exp_vis(ctx: CallContext) -> list[dict]:
    """The demo's expVis: the expected returns the signed-in account may see (all of them for the system actor), with
    `window` and `prob` (the likely outcome's return window and probability) at the top level."""
    a = None if ctx.actor.system else ctx.actor.account
    return [_brief(e) for e in (EXPECTED if a is None else expected_for(a, ctx.actor.ctx))]
