from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# B16b: the Groq model Ask uses when GROQ_MODEL is empty (chosen from the account's model list: tool calling on the free tier)
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DI_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://circ:circ@localhost:5432/di"
    source_sim_url: str = "http://localhost:8100"
    worker_poll_seconds: float = 1.0
    job_max_attempts: int = 5
    # B1 golden files: the access policy and reference data (mounted at /fixtures in Docker)
    golden_dir: str = "/fixtures/golden"
    # B7: sign-in tokens (HS256). Override DI_JWT_SECRET outside local development.
    jwt_secret: str = "dev-only-change-me-circularity-di-api-secret"  # noqa: S105 - dev-only default, replaced in deployments (F7)
    jwt_ttl_minutes: int = 720
    # B9: where source-sim delivers change events, and the shared signing secret
    webhook_url: str = "http://api:8000/api/webhooks/source-sim"
    webhook_secret: str = "dev-only-source-sim-webhook-secret"  # noqa: S105 - dev-only default, replaced in deployments (F7)
    # B13b: what "now" is (di/clock.py): "pinned" to the demo's as-of time, or "sim" = source-sim's simulated clock
    clock: str = "pinned"
    clock_cache_seconds: float = 2.0  # how long the simulated clock's anchor is reused before it is read again
    # B13b: send approved decisions' steps to the systems (di/instructions); off unless the services turn it on
    instructions: bool = False
    # B5c: AWS IoT Core (source iot) starts not provisioned, as in the demo. True registers it live at start-up
    # (DI_IOT_CONNECTED=true); at run time POST /api/sources/iot/connect does the same.
    iot_connected: bool = False
    # a step with no matching write in the mocks is acknowledged by a simulated adapter after this many simulated hours
    simulated_ack_hours: float = 2.0
    # B16b, Ask Circularity (di/ask): which language model answers ("groq", or "none" for the rule-based fallback only).
    # These three are read without the DI_ prefix, as .env.example names them; the key is never logged or returned.
    ask_provider: str = Field("groq", validation_alias="ASK_PROVIDER")
    groq_api_key: SecretStr = Field(SecretStr(""), validation_alias="GROQ_API_KEY")
    groq_model: str = Field("", validation_alias="GROQ_MODEL")  # empty: DEFAULT_GROQ_MODEL
    ask_timeout_seconds: float = 20.0  # one model request; on timeout Ask falls back
    ask_max_rounds: int = 4  # model requests per question (tool rounds), the last one without tools


@lru_cache
def get_settings() -> Settings:
    return Settings()
