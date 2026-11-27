"""llm_model may hold a second provider, `gemini` (ai-tasks T1; registry entry I-9; 27 Nov 2026).

The router's chain had one provider, so one provider's limits were the whole budget (27 Nov 2026: about three requests a
minute per Groq model on the free tier). The provider check now allows `gemini` (Google's Gemini API through its
OpenAI-compatible endpoint, di.services.llm.compat). The rows themselves are put in at api start by
di.services.llm.seed.ensure_models (a row without its key in the environment is never used), not here: two test modules
delete rows from the shared dev database, and a migration runs once.
"""

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE llm_model DROP CONSTRAINT IF EXISTS llm_model_provider")
    op.execute("ALTER TABLE llm_model ADD CONSTRAINT llm_model_provider CHECK (provider IN ('groq','gemini','test'))")


def downgrade() -> None:
    op.execute("DELETE FROM llm_model WHERE provider = 'gemini'")
    op.execute("ALTER TABLE llm_model DROP CONSTRAINT IF EXISTS llm_model_provider")
    op.execute("ALTER TABLE llm_model ADD CONSTRAINT llm_model_provider CHECK (provider IN ('groq','test'))")
