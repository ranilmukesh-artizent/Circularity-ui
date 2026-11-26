"""What each choice of an ambiguous mapping would have done to the past (plan 9, P9-11.11, story MR-03; the phase-8 test run).

    report(items, pack) -> list[dict]     one entry per active gate of the pack that has a reporter; [] when none has
    REPORTERS                             gate id -> reporter(items, pack, gate) -> dict | None, set by the gate module

A pack hint can leave a mapping to a person because two source fields could be the one the gate reads (medical rental: the
start or the end of a decontamination cycle). `compose.testRun` calls `report` with the batch's past items (`di.repositories.
replay.ok_items`: facts as `{name: {value, at}}`); a reporter counts, for each choice, how many past items the gate would have
stopped. The counts are the gate's own evaluation (the same check `decide_case` runs), never a model's number; the sentence
is composed from them. Owns: the registry and the loop. Never does: read a session or a clock, write anything, or choose for
a person (the choice is `mapping.decide`, held for a person: rule 10). A reporter lives with its gate, so no pack's words are
here. `gates` is imported inside `report`: the gate modules import this one while `gates` is still loading.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from di.services.modeler.pack import Pack

if TYPE_CHECKING:
    from di.services.modeler.gates import GateDef

Reporter = Callable[[Sequence[Mapping[str, Any]], Pack, "GateDef"], dict[str, Any] | None]
REPORTERS: dict[str, Reporter] = {}


def report(items: Sequence[Mapping[str, Any]], pack: Pack) -> list[dict[str, Any]]:
    """The reports of the pack's active gates that have a reporter, in catalogue order."""
    from di.services.modeler.gates import pack_gates

    out = []
    for gate in pack_gates(pack):
        reporter = REPORTERS.get(gate.id)
        if reporter is not None and (got := reporter(items, pack, gate)) is not None:
            out.append(got)
    return out
