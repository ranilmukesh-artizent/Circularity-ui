"""Carbon factor set: the kg of CO2e a route avoids against buying new (plan 9, P9-0.6).

Owns the read of `packs/carbon.json` and `co2_avoided`, the one place a valuer asks for a route's CO2e.
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
    """E_new of the class (or `*`) x the route's share x quantity, rounded as the demo rounds; None without a factor."""
    f = _factors()
    pack = f["packs"].get(pack_key)
    if pack is None:
        return None
    e_new = pack["e_new"].get(cls or "*")
    share = pack["share"].get(route)
    if e_new is None or share is None:
        return None
    src = f["source"]
    return Co2(js_round(e_new * share * qty), f["set"], src["source"], src["year"], src["method"])
