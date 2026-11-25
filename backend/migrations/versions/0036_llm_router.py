"""LLM router tables (plan 9, P9-2.3; registry entry I-9): llm_model, llm_budget and the seeded Groq row.

llm_model holds each model with its limits, roles and cooldown (a key is never stored: key_ref names a setting);
llm_budget counts the requests and tokens used per model and window (minute, day). The seed is the model Ask uses
today (DEFAULT_GROQ_MODEL; GROQ_MODEL still overrides it at run time).

Plan 9's writers run in parallel and merge in any order, so every migration from
0029 to 0061 exists, chained, from the start; a filled one is idempotent (IF NOT EXISTS), and
`scripts/dev/migrate-reapply.sh 0028` applies it on a database that already ran it empty.

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-25
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE IF NOT EXISTS llm_model (
  id text PRIMARY KEY,
  provider text NOT NULL CONSTRAINT llm_model_provider CHECK (provider IN ('groq','test')),
  model text NOT NULL,
  key_ref text NULL,
  rpm integer NOT NULL,
  tpm integer NOT NULL,
  rpd integer NOT NULL,
  ctx_tokens integer NOT NULL DEFAULT 8192,
  tools boolean NOT NULL DEFAULT true,
  structured boolean NOT NULL DEFAULT true,
  roles text[] NOT NULL,
  priority integer NOT NULL DEFAULT 100,
  enabled boolean NOT NULL DEFAULT true,
  request_timeout numeric NOT NULL DEFAULT 20,
  cooldown_until timestamptz NULL,
  eval_score numeric NULL,
  eval_prev numeric NULL,
  eval_at timestamptz NULL
);
CREATE TABLE IF NOT EXISTS llm_budget (
  model_id text NOT NULL REFERENCES llm_model(id) ON DELETE CASCADE,
  "window" text NOT NULL CONSTRAINT llm_budget_window CHECK ("window" IN ('minute','day')),
  window_start timestamptz NOT NULL,
  used_requests integer NOT NULL DEFAULT 0,
  used_tokens integer NOT NULL DEFAULT 0,
  PRIMARY KEY (model_id, "window", window_start)
);
INSERT INTO llm_model (id, provider, model, key_ref, rpm, tpm, rpd, roles, priority)
VALUES ('groq-default', 'groq', 'openai/gpt-oss-120b', 'env:GROQ_API_KEY', 30, 8000, 1000,
        ARRAY['ask','agent','author','judge'], 1)
ON CONFLICT (id) DO NOTHING;
"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS llm_budget")
    op.execute("DROP TABLE IF EXISTS llm_model")
