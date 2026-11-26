"""Carbon factor set: the kg of CO2e a route avoids against buying new (plan 9, P9-0.6; X-12 in P9-1.12).

Owns the read of `packs/carbon.json` and `co2_avoided`, the one place a valuer asks for a route's CO2e. A pack names
its factor set in `valuer.carbon.set`; a pack naming a set this file does not hold has no CO2e. The pack's
`valuer.carbon.d_rule` says how the demand share d is found: `demand` (1 on a confirmed named order, the forecast
otherwise), `low` (`params.d_low`), `transport_only` (no avoided figure, the transport kg only) or `none`.

Formula (B 5.7, "avoided, not inventory"): kg = (e_new x d - e_prep - e_log) x qty, rounded as the demo rounds.
Every factor that enters the figure is returned with its own provenance (source, year, set): a figure without a factor
is never shown. Never changes a route, a net or a ranking: the figure is information on the route. The sample factors
are synthetic and no third-party data is bundled; a real factor set needs review by Kinective's Legal team before any
report.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from di.services.engine.jsmath import js_round
from di.services.modeler.pack import Pack

_FILE = Path(__file__).parent / "packs" / "carbon.json"


@dataclass(frozen=True)
class Factor:
    name: str  # e_new, d, e_prep or e_log
    value: float
    source: str
    year: int
    version: str
    licence: str


@dataclass(frozen=True)
class Co2:
    kg: float | None  # avoided kg CO2e; None when the rule gives no avoided figure (transport only)
    transport_kg: float | None  # e_log x qty, shown under the transport-only rule
    set: str
    factors: tuple[Factor, ...]

    @property
    def label(self) -> str:
        return "avoided, not inventory" if self.kg is not None else "transport only, not avoided"

    def prov(self) -> dict[str, Any]:
        """The card's provenance: the set, the label, each factor with its value, source and year."""
        return {
            "set": self.set,
            "label": self.label,
            "factors": [{"name": f.name, "value": f.value, "source": f.source, "year": f.year} for f in self.factors],
            "transportKg": self.transport_kg,
        }


@cache
def _factors() -> dict[str, Any]:
    with _FILE.open(encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def _lookup(table: dict[str, Any], key: str | None) -> dict[str, Any] | None:
    """A factor entry by its key (a class or a route), or the table's `*` entry for every key; None without one."""
    if key is not None and key in table:
        return table[key]
    return table.get("*")


def _factor(name: str, entry: dict[str, Any], version: str) -> Factor:
    return Factor(name, entry["value"], entry["source"], entry["year"], version, entry["licence"])


def co2_avoided(pack: Pack, cls: str | None, route: str, qty: float, *, confirmed: bool) -> Co2 | None:
    """The CO2e a route avoids for `qty` units of class `cls` (the pack's `valuer.carbon.d_rule` decides d).

    `confirmed` says the route's destination is a confirmed named order (the demand line). None without the pack's
    factor set, without a factor for the class or route, or under the `none` rule.
    """
    f = _factors()
    entry = f["packs"].get(pack.key)
    set_name = f["set"] if entry is None else entry.get("set", f["set"])  # a pack may carry a set of its own (P9-12.6)
    if pack.valuer.carbon.set != set_name:
        return None
    rule = pack.valuer.carbon.d_rule
    if entry is None or rule == "none":
        return None
    e_log_entry = _lookup(entry["e_log"], route)
    if e_log_entry is None:
        return None
    e_log = _factor("e_log", e_log_entry, set_name)
    if rule == "transport_only":
        return Co2(None, e_log.value * qty, set_name, (e_log,))
    e_new_entry = _lookup(entry["e_new"], cls)
    e_prep_entry = _lookup(entry["e_prep"], route)
    if e_new_entry is None or e_prep_entry is None:
        return None
    if rule == "low":
        d_low = pack.valuer.params.get("d_low")
        if d_low is None:
            return None
        d_entry = {**entry["d_forecast"], "value": d_low, "source": "Pack parameter d_low (low-confidence demand)"}
    else:
        d_entry = entry["d_confirmed"] if confirmed else entry["d_forecast"]
    e_new = _factor("e_new", e_new_entry, set_name)
    d = _factor("d", d_entry, set_name)
    e_prep = _factor("e_prep", e_prep_entry, set_name)
    kg = js_round((e_new.value * d.value - e_prep.value - e_log.value) * qty)
    return Co2(kg, None, set_name, (e_new, d, e_prep, e_log))
