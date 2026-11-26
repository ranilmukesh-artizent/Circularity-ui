"""Two Groq fallback models for the LLM router (plan 9, registry entry I-9; 26 Nov 2026).

One model alone hit Groq's free-tier limits (30 requests a minute, 8,000 tokens a minute, 1,000 requests a day, per model)
in a demo: a 429 put it on cooldown and every caller fell to its deterministic path. Groq's limits are per model, so two more
tool-calling models of the same account triple the budget. Checked on 26 Nov 2026 against the account's model list and one
tool-calling request each (the limits from the response headers):
- qwen/qwen3.8-27b, priority 2, every role;
- openai/gpt-oss-20b, priority 3, the cheapest; not a judge (an eval judge stays on a larger model).
The key is never stored: key_ref names the setting. Idempotent (ON CONFLICT DO NOTHING); an admin changes them with
`llm.setModel`.
"""

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
INSERT INTO llm_model (id, provider, model, key_ref, rpm, tpm, rpd, ctx_tokens, roles, priority)
VALUES ('groq-qwen3-27b', 'groq', 'qwen/qwen3.8-27b', 'env:GROQ_API_KEY', 30, 8000, 1000, 131072,
        ARRAY['ask','agent','author','judge'], 2),
       ('groq-oss-20b', 'groq', 'openai/gpt-oss-20b', 'env:GROQ_API_KEY', 30, 8000, 1000, 131072,
        ARRAY['ask','agent','author'], 3)
ON CONFLICT (id) DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM llm_model WHERE id IN ('groq-qwen3-27b', 'groq-oss-20b')")
