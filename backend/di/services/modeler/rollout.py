"""Publishing in steps (plan 9, P9-7.3; registry entry I-17; story X-06): replay, shadow, canary by region and share, full.

Pure: no database, no clock. It owns the stage names, the moves between them (`can_move`) and which arm a case falls in
(`assign`). The tables (`rollout`, `rollout_assignment`) are read and written by di.repositories.rollouts, the actions are in
di.services.actions.rollout. It never publishes anything itself, and no agent may: publishing, widening and rolling back are
a person's (maker-checker; `rollout.` is in di.services.agents.forbidden).

    replay -> shadow -> canary -> full        canary <-> paused (a pause returns new cases to the base version)
    any -> rolled_back

`assign` is deterministic: the same case, subject and salt always land in the same bucket 0-99, so a share that only rises
only adds cases to the canary. The caller stores the assignment, and a stored one wins from then on (sticky).
"""

import hashlib
from dataclasses import dataclass
from typing import Literal

Stage = Literal["replay", "shadow", "canary", "full", "paused", "rolled_back"]
Arm = Literal["canary", "control", "out"]

STAGES: tuple[Stage, ...] = ("replay", "shadow", "canary", "full", "paused", "rolled_back")
_NEXT: dict[Stage | None, frozenset[Stage]] = {
    None: frozenset({"replay"}),
    "replay": frozenset({"shadow"}),
    "shadow": frozenset({"canary"}),
    "canary": frozenset({"full", "paused"}),
    "paused": frozenset({"canary"}),
    "full": frozenset(),
    "rolled_back": frozenset(),
}


@dataclass(frozen=True)
class Rollout:
    """One row of `rollout`: a candidate version released in one region (`region` None: every case) at `share` percent."""

    id: int
    subject_kind: str
    subject_id: str
    candidate_ver: int | None
    base_ver: int | None
    stage: Stage
    region_key: str
    region: str | None
    share: int
    salt: str


def can_move(current: Stage | None, target: Stage) -> bool:
    """Whether a rollout in `current` (None: no rollout yet) may move to `target`."""
    if target == "rolled_back":
        return current != "rolled_back"
    return target in _NEXT.get(current, frozenset())


def bucket(case_id: str, subject_id: str, salt: str) -> int:
    """The case's bucket, 0 to 99, for this subject and salt."""
    return int(hashlib.sha256(f"{case_id}:{subject_id}:{salt}".encode()).hexdigest()[:8], 16) % 100


def assign(case_id: str, subject_id: str, salt: str, region_value: str | None, rollout: Rollout) -> Arm:
    """`out` when the case's region is not the rollout's (compared exactly); else `canary` when its bucket is below the share,
    else `control`."""
    if rollout.region is not None and (region_value is None or str(region_value) != rollout.region):
        return "out"
    return "canary" if bucket(case_id, subject_id, salt) < rollout.share else "control"
