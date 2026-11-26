"""Seeded replay datasets per pack (plan 9, P9-9.15, P9-10.13, P9-11.13; registry entry I-16; story X-06).

`DATASETS` maps a pack's `replay.dataset` name to the function that makes its history rows: CSV-shaped dictionaries in the
columns `di.services.replay.history` reads (`item_id, class, decided_at, ..., market, fact.<name>, fact.<name>.at`). Each
module is deterministic (a fixed seed), reads nothing and invents every value, and none imports the replay run (the
Modeler's policy core is pure). A pack adds one entry here; the entries import their module when called, so
`python -m <module>` runs without the package having loaded it first.
"""

from collections.abc import Callable


def _telecom_network() -> list[dict[str, str]]:
    from di.services.modeler.replay_samples import telecom_network

    return telecom_network.rows()


def _medical_rental() -> list[dict[str, str]]:
    from di.services.modeler.replay_samples import medical_rental

    return medical_rental.rows()


DATASETS: dict[str, Callable[[], list[dict[str, str]]]] = {
    "telecom_network": _telecom_network,
    "medical_rental": _medical_rental,
}
