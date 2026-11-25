"""Never keep a secret (plan 9, P9-2.6): `clean(obj)` drops every dict key that looks like one, at any depth.

Moved from the action pipeline (`_clean`), which stores an action's input in the journal, a proposal and an event, and
now shared with `di.core.tracing`, which stores span attributes. Never does: look at values (only keys), or change
what it is given (it returns a copy).
"""

from typing import Any

SECRET_WORDS = ("secret", "password", "token", "credential", "api_key", "apikey", "private_key")


def clean(obj: Any) -> Any:
    """`obj` without any dict entry whose key contains a secret word (case-insensitive); lists are walked."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if not any(w in str(k).lower() for w in SECRET_WORDS)}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj
