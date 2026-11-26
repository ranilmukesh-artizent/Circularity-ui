"""Replay histories shipped with the packs (plan 9, P9-11.13): `DATASETS` maps a pack's `replay.dataset` to its module.

Each module owns `rows()` (the history as CSV rows), `items(...)` and `replay(...)`; none of them imports the replay run (the
Modeler's policy core is pure), the caller passes `di.services.replay.run.replay`.
"""

DATASETS: dict[str, str] = {
    "medical_rental": "di.services.modeler.replay_samples.medical_rental",
}
