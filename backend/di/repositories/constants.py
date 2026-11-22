"""Reference constants several modules read, defined once (from the golden reference files, read-only).

- the demo's TOOLS, AGENTS and HARD_RULES (fixtures/golden/tools.json); `TOOLS_BY_ID`, `AGENTS_BY_ID` index them;
- the access page's DELEG, AF_LEVELS, AF_LV_RANK and AF_AUTO_TYPES (fixtures/golden/screens/access.json);
- the field mappings MAPPINGS (the demo's starting values) and MAP_TARGET (screens/integration.json);
- ROUTES and MODELS (the golden world), SRC_TYPES (sources.json).
"""

from di.core import golden
from di.repositories.common import STARTING_MAPPINGS, WORLD

_TOOLS = golden.load("tools")
TOOLS: list[dict] = _TOOLS["tools"]
TOOLS_BY_ID: dict[str, dict] = {t["id"]: t for t in TOOLS}
AGENTS: list[dict] = _TOOLS["agents"]
AGENTS_BY_ID: dict[str, dict] = {a["id"]: a for a in AGENTS}
HARD_RULES: list[str] = _TOOLS["hard_rules"]

_ACCESS = golden.load("screens/access")
# the demo's DELEG: the kinds of request Admin may let the Approver decide (key, label, description)
DELEG: list[dict] = [{k: d[k] for k in ("k", "label", "desc")} for d in _ACCESS["delegations"]]
LEVELS: list[dict] = _ACCESS["levels"]  # the demo's AF_LEVELS
LEVEL_RANK: dict[str, int] = {"off": 0, "suggest": 1, "prepare": 2, "act": 3}  # the demo's AF_LV_RANK
AUTO_TYPES: list[dict] = _ACCESS["auto_types"]  # the demo's AF_AUTO_TYPES

MAPPINGS: dict[str, list] = STARTING_MAPPINGS
MAP_TARGET: dict[str, str] = golden.load("screens/integration")["map_target"]

ROUTES: list[dict] = WORLD["routes"]
MODELS: list[dict] = WORLD["models"]
SRC_TYPES: dict[str, dict] = golden.load("sources")["types"]
