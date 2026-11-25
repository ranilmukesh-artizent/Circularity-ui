"""Valuers of the non-industrial templates (plan 8, phase 6; D11): ports of the PO prototype's engines that price every
path of a case. `tool_fleet` (Recover's `value`/`decide`, rng(26110) sample cases) and `device` (`dScore`/`dDecide`,
rng(4242) sample lots). Pure: no Session, no I/O.

Plan 9 (registry entry I-21): a pack whose routes need code registers a plug-in in `VALUERS`, keyed by the pack's
`valuer.kind`: `value_routes(case, pack, as_of) -> list[PathValue]`. `decide_case` (the one decider) reads this table. The
standard valuer (`standard.py`, the pack's own value lines, no code) is `VALUERS["standard"]`.
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from di.services.modeler.pack import Pack
from di.services.modeler.valuers import standard
from di.services.modeler.valuers.tool_fleet import PathValue

ValuerFn = Callable[[Mapping[str, Any], Pack, datetime | None], list[PathValue]]

VALUERS: dict[str, ValuerFn] = {"standard": standard.value_routes}
