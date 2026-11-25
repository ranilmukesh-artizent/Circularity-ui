"""Carbon factor set: the kg of CO2e a route avoids against buying new (plan 9, P9-0.6).

Owns the read of `packs/carbon.json` and `co2_avoided`, the one place a valuer asks for a route's CO2e. A pack names
its factor set in `valuer.carbon.set`; a pack naming a set this file does not hold has no CO2e.
Never changes a route, a net or a ranking: the figure is information on the route. The sample factors are synthetic
and no third-party data is bundled; a real factor set needs review by Kinective's Legal team before any report.
P9-1.12 (X-12) replaces the simple share with B 5.7's formula.
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from di.services.engine.jsmath import js_round
from di.services.modeler.pack import Pack, load_pack

_FILE = Path(__file__).parent / "packs" / "carbon.json"


@dataclass(frozen=True)
class Co2:
    kg: float
    set: str
    source: str
    year: int
    method: str

    @property
    def label(self) -> str:
        """The factor source line, for example `cfs-2026.1 · Sample value (synthetic), 2026`."""
        return f"{self.set} · {self.source}, {self.year}"


@cache
def _factors() -> dict[str, Any]:
    with _FILE.open(encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


def co2_avoided(pack_key: str, cls: str | None, route: str, qty: float) -> Co2 | None:
    """`co2_avoided_of` for the pack `pack_key`; None for an unknown pack."""
    try:
        pack = load_pack(pack_key)
    except KeyError:
        return None
    return co2_avoided_of(pack, cls, route, qty)


def co2_avoided_of(pack: Pack, cls: str | None, route: str, qty: float) -> Co2 | None:
    """E_new of the class (or `*`) x the route's share x quantity, rounded as the demo rounds, from the factor set the
    pack names (`valuer.carbon.set`); None without that set or without a factor."""
    f = _factors()
    if pack.valuer.carbon.set != f["set"]:
        return None
    entry = f["packs"].get(pack.key)
    if entry is None:
        return None
    e_new = entry["e_new"].get(cls or "*")
    share = entry["share"].get(route)
    if e_new is None or share is None:
        return None
    src = f["source"]
    return Co2(js_round(e_new * share * qty), f["set"], src["source"], src["year"], src["method"])
