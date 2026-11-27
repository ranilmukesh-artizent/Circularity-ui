"""The provider models every stack must have (ai-tasks T1; registry entry I-9): put back at every api start.

Why at start and not only in a migration: migration 0063 seeded the two Groq fallback rows once, and two test modules
(tests/test_llm_router.py, tests/test_run_trace.py) delete every row but the seed from the database they share with the dev
stack. On 27 Nov 2026 the main stack had one model, it hit its limit, and every answer came from the rules.

    ensure_models(s) -> int   inserts the rows that are missing (ON CONFLICT DO NOTHING); never changes a row that is there,
                              so an admin's `llm.setModel` (priority, limits, enabled) survives a restart

A row without its key in the environment is never used (router._usable), so the Gemini rows are harmless on a stack that has
no GEMINI_API_KEY.

Groq (key GROQ_API_KEY): the tool-calling chat models of the account, each checked on 27 Nov 2026 with one tool-calling
request (the limits are the response headers': 1,000 requests a day and 8,000 tokens a minute per model; 30 requests a
minute is Groq's published free-tier figure; `openai/gpt-oss-120b`, the row of migration 0036, also has 200,000 tokens a day).

Gemini (key GEMINI_API_KEY, migration 0066, di.services.llm.compat): checked on 27 Nov 2026 with one tool-calling request
per model on a free-tier key. The Flash-Lite models answered in about a second; `gemini-3.8-flash` answered 503 (high
demand); every Pro and Gemini 4 model answered 429 (no free quota), and the 2.5 models are closed to new keys, so none of
those is a row. Google does not put its free-tier limits in response headers, so the limits below are what third-party
readings of AI Studio reported in September and October 2026 (Flash-Lite 15 requests a minute and 500 a day, Flash 5 and
20, 250,000 tokens a minute): NOT verified here. They only decide when the router stops trying a model on its own; the
provider's own 429 still cools the model down. Set the real figures from AI Studio's rate-limit page with `llm.setModel`.

Order (priority, then id): Groq's large model, Gemini Flash-Lite (its token allowance is not the 8,000 a minute that makes
the Groq models wait), the two Groq fallbacks, the older Flash-Lite, and Gemini Flash last (best of the free Gemini models,
but about 20 requests a day). Not judges: an eval judge stays on a larger model.
"""

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
_ALL = ("ask", "agent", "author", "judge")
_WORK = ("ask", "agent", "author")
# id, provider, model, key_ref, rpm, tpm, rpd, ctx_tokens, roles, priority
MODELS: tuple[tuple[str, str, str, str, int, int, int, int, tuple[str, ...], int], ...] = (
    ("groq-qwen3-27b", "groq", "qwen/qwen3.8-27b", "env:GROQ_API_KEY", 30, 8000, 1000, 131072, _ALL, 2),
    ("groq-oss-20b", "groq", "openai/gpt-oss-20b", "env:GROQ_API_KEY", 30, 8000, 1000, 131072, _WORK, 3),
    ("gemini-35-flash-lite", "gemini", "gemini-3.5-flash-lite", "env:GEMINI_API_KEY", 15, 250000, 500, 131072, _WORK, 2),
    ("gemini-31-flash-lite", "gemini", "gemini-3.1-flash-lite", "env:GEMINI_API_KEY", 15, 250000, 500, 131072, _WORK, 4),
    ("gemini-38-flash", "gemini", "gemini-3.8-flash", "env:GEMINI_API_KEY", 5, 250000, 20, 131072, _WORK, 5),
)


def ensure_models(s: Session) -> int:
    """Insert the missing rows; the number inserted. A row the database refuses (a provider its check does not know yet:
    a database before migration 0066) is skipped, the others still go in."""
    n = 0
    for mid, provider, model, key_ref, rpm, tpm, rpd, ctx, roles, priority in MODELS:
        try:
            with s.begin_nested():
                got = s.execute(
                    text(
                        "INSERT INTO llm_model (id, provider, model, key_ref, rpm, tpm, rpd, ctx_tokens, roles, priority) "
                        "VALUES (:i, :pr, :m, :k, :rpm, :tpm, :rpd, :ctx, :r, :p) ON CONFLICT (id) DO NOTHING RETURNING 1"
                    ),
                    {"i": mid, "pr": provider, "m": model, "k": key_ref, "rpm": rpm, "tpm": tpm, "rpd": rpd, "ctx": ctx,
                     "r": list(roles), "p": priority},
                ).first()  # fmt: skip
            n += 1 if got else 0
        except Exception:  # noqa: BLE001 - one row must not keep the others out
            log.warning("llm: the model row %s was not added", mid, exc_info=True)
    return n
