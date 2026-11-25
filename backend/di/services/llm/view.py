"""What the person sees of the router (plan 9, P9-2.3): the models with their limits, use and cooldown.

Owns: the one read model behind the action `llm.models` and the `llm` block of the Agents screen. Never: returns a key
(a row holds only `key_ref`, and even that is not shown).
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

VIEW_SQL = """
SELECT m.id, m.provider, m.model, m.roles, m.rpm, m.tpm, m.rpd, m.enabled, m.priority, m.cooldown_until,
       coalesce(bm.used_requests, 0) AS mr, coalesce(bm.used_tokens, 0) AS mt,
       coalesce(bd.used_requests, 0) AS dr, coalesce(bd.used_tokens, 0) AS dt,
       m.cooldown_until IS NOT NULL AND m.cooldown_until > now() AS cooling
FROM llm_model m
LEFT JOIN llm_budget bm ON bm.model_id = m.id AND bm."window" = 'minute' AND bm.window_start = date_trunc('minute', now())
LEFT JOIN llm_budget bd ON bd.model_id = m.id AND bd."window" = 'day' AND bd.window_start = date_trunc('day', now())
ORDER BY m.priority, m.id
"""


def models_view(s: Session) -> list[dict[str, Any]]:
    out = []
    for r in s.execute(text(VIEW_SQL)).mappings():
        out.append({
            "id": r["id"], "provider": r["provider"], "model": r["model"], "roles": list(r["roles"]),
            "rpm": r["rpm"], "tpm": r["tpm"], "rpd": r["rpd"], "enabled": r["enabled"], "priority": r["priority"],
            "used_minute": {"requests": r["mr"], "tokens": r["mt"]},
            "used_day": {"requests": r["dr"], "tokens": r["dt"]},
            "cooling_until": r["cooldown_until"].isoformat() if r["cooling"] else None,
        })  # fmt: skip
    return out
