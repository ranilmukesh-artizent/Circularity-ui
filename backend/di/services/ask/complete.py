"""complete_json: one JSON-mode completion down the model chain (plan 9, P9-0.5).

Owns: the short JSON requests of flow.propose (modeler_read) and workflow.plan (workflow_builder).
Never: raises, logs or returns the key. Returns {} when the provider is off, no key is set or every model fails.
"""

import json
import logging
from typing import Any

log = logging.getLogger("di.ask.complete")


def complete_json(system: str, user: str, *, max_tokens: int, timeout: float | None = None) -> dict[str, Any]:
    try:
        from di.core.config import get_settings, model_chain
        from di.services.ask import groq_model

        st = get_settings()
        key = st.groq_api_key.get_secret_value().strip()
        if not key or (st.ask_provider or "groq").strip().lower() != "groq":
            return {}
        client = groq_model._client(key, timeout if timeout is not None else min(st.ask_timeout_seconds, 10.0))
        for _, model in model_chain(st):
            extra = {"reasoning_effort": "low", "include_reasoning": False} if model.startswith("openai/gpt-oss") else {}
            try:
                r = client.chat.completions.create(  # type: ignore[call-overload]
                    model=model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0,
                    max_completion_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    **extra,
                )
                out = json.loads(r.choices[0].message.content or "{}")
                return out if isinstance(out, dict) else {}
            except Exception as e:  # noqa: BLE001 - optional helper: try the next model, never raise
                log.info("complete_json: %s failed (%s)", model, type(e).__name__)
        return {}
    except Exception:  # noqa: BLE001
        return {}
