"""Ageing stock of an ITAD pack: `SR-IT-AGE` (plan 9, P9-12.3, story NS-IT-03; registry entry I-4). Pure.

    suggestions(pack, stock) -> list[dict]   one suggestion per asset in stock `months_in_stock_ge` months or more

`stock` is the assets in stock, each `{serial, asset_class, months_in_stock, value?}` (the caller reads them from the canonical
store). The rule is the pack's `runtime.suggestion_rules` entry `SR-IT-AGE` (`params.months_in_stock_ge`, the route to suggest,
`resell`: "move ageing stock to wholesale"). Ordered oldest first (months in stock), then the larger value first, then by serial.
Never does: sell or move an asset (a person adopts a suggestion, R7), read a store, or use a model: every figure is a read fact.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from di.services.modeler.pack import Pack

RULE = "SR-IT-AGE"


def rule(pack: Pack) -> dict[str, Any]:
    r = next((x for x in pack.runtime.suggestion_rules if x.get("id") == RULE), None)
    if r is None:
        raise KeyError(f"the pack has no rule {RULE}")
    return r


def suggestions(pack: Pack, stock: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    r = rule(pack)
    floor = int(r["params"]["months_in_stock_ge"])
    old = [a for a in stock if int(a.get("months_in_stock") or 0) >= floor]
    old.sort(key=lambda a: (-int(a["months_in_stock"]), -float(a.get("value") or 0), str(a["serial"])))
    return [
        {"rule": RULE, "serial": a["serial"], "route": r["route"], "months_in_stock": int(a["months_in_stock"]),
         "text": f"{a['serial']} has been in stock {int(a['months_in_stock'])} months: move it to wholesale"}
        for a in old
    ]  # fmt: skip
