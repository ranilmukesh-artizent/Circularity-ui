"""Where a case lives, for the tenant boundary and warehouse lock of case-scoped actions.

Until di holds cases itself (B9 fills the canonical store from the connectors, B11 builds cases), the owner and
location come from the golden cases. `set_provider` swaps in the database lookup when it exists.
"""

from collections.abc import Callable

from di import golden

Provider = Callable[[str], tuple[str, str] | None]  # case id -> (owner tenant, current location)


def _golden(case_id: str) -> tuple[str, str] | None:
    c = _GOLDEN.get(case_id)
    return (c["owner"], c["location"]) if c else None


_GOLDEN = {c["id"]: c for c in golden.load("cases")}
_provider: Provider = _golden


def set_provider(p: Provider) -> None:
    global _provider
    _provider = p


def case_scope(case_id: str) -> tuple[str, str] | None:
    return _provider(case_id)
