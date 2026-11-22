import base64
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# B16b: the Groq model Ask uses when GROQ_MODEL is empty (chosen from the account's model list: tool calling on the free tier)
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"

# D2 (F7): the signing secrets shipped for local development. Outside DI_ENV=dev they are refused, as is any secret
# shorter than MIN_SECRET_BYTES: set DI_JWT_SECRET and DI_WEBHOOK_SECRET (.env.example).
DEV_JWT_SECRET = "dev-only-change-me-circularity-di-api-secret"  # noqa: S105 - dev-only default, refused outside dev
DEV_WEBHOOK_SECRET = "dev-only-source-sim-webhook-secret"  # noqa: S105 - dev-only default, refused outside dev
MIN_SECRET_BYTES = 32
# plan 6 A1: source credentials are encrypted with DI_SECRET_KEY; in dev an empty key is derived from this seed
DEV_SECRET_SEED = "dev-only-circularity-source-credentials"  # noqa: S105 - dev-only seed, refused outside dev


class Settings(BaseSettings):
    # hide_input_in_errors: a refused setting must not echo the secrets into a traceback or a log
    model_config = SettingsConfigDict(env_prefix="DI_", env_file=".env", extra="ignore", hide_input_in_errors=True)

    # D2: dev (the shipped secrets are accepted), test or prod (they are refused)
    env: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+psycopg://circ:circ@localhost:5432/di"
    source_sim_url: str = "http://localhost:8100"
    worker_poll_seconds: float = 1.0
    job_max_attempts: int = 5
    # B1 golden files: the access policy and reference data (mounted at /fixtures in Docker)
    golden_dir: str = "/fixtures/golden"
    # B7: sign-in tokens (HS256), DI_JWT_SECRET; empty means the dev default
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_ttl_minutes: int = 720
    # B9: where source-sim delivers change events, and the shared signing secret (DI_WEBHOOK_SECRET; empty: dev default)
    webhook_url: str = "http://api:8000/api/webhooks/source-sim"
    webhook_secret: SecretStr = SecretStr(DEV_WEBHOOK_SECRET)
    # plan 6 A6: the wait before the first retry of a source GET (429, 5xx, timeout); doubled for each next retry
    source_retry_base_seconds: float = 0.5
    # plan 6 A1: the Fernet key for source credentials (urlsafe base64 of 32 bytes); empty means the dev key (dev only)
    secret_key: SecretStr = SecretStr("")
    # B13b: what "now" is (di/core/clock.py): "pinned" to the demo's as-of time, or "sim" = source-sim's simulated clock
    clock: Literal["pinned", "sim"] = "pinned"
    clock_cache_seconds: float = 2.0  # how long the simulated clock's anchor is reused before it is read again
    # B13b: send approved decisions' steps to the systems (di/services/instructions); off unless the services turn it on
    instructions: bool = False
    # B5c: AWS IoT Core (source iot) starts not provisioned, as in the demo. True registers it live at start-up
    # (DI_IOT_CONNECTED=true); at run time POST /api/sources/iot/connect does the same.
    iot_connected: bool = False
    # a step with no matching write in the mocks is acknowledged by a simulated adapter after this many simulated hours
    simulated_ack_hours: float = 2.0
    # B16b, Ask Circularity (di/services/ask): which language model answers ("groq", or "none"/"off"/"fallback" for the
    # rule-based fallback only; di.services.ask.model.get_model). These three are read without the DI_ prefix, as .env.example
    # names them; the key is never logged or returned.
    ask_provider: Literal["groq", "none", "off", "fallback"] = Field("groq", validation_alias="ASK_PROVIDER")
    groq_api_key: SecretStr = Field(SecretStr(""), validation_alias="GROQ_API_KEY")
    groq_model: str = Field("", validation_alias="GROQ_MODEL")  # empty: DEFAULT_GROQ_MODEL
    ask_timeout_seconds: float = 20.0  # one model request; on timeout Ask falls back
    ask_max_rounds: int = 4  # model requests per question (tool rounds), the last one without tools

    @field_validator("jwt_secret", "webhook_secret", mode="before")
    @classmethod
    def _empty_is_the_dev_default(cls, v: object, info: ValidationInfo) -> object:
        raw = v.get_secret_value() if isinstance(v, SecretStr) else v
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return DEV_JWT_SECRET if info.field_name == "jwt_secret" else DEV_WEBHOOK_SECRET
        return v

    @field_validator("ask_provider", mode="before")
    @classmethod
    def _provider_name(cls, v: object) -> object:
        # as get_model read it before: case and spaces do not matter, and empty means groq
        return (v.strip().lower() or "groq") if isinstance(v, str) else v

    @model_validator(mode="after")
    def _no_dev_secrets_outside_dev(self) -> Self:
        if self.env == "dev":
            return self
        for name, default in (("jwt_secret", DEV_JWT_SECRET), ("webhook_secret", DEV_WEBHOOK_SECRET)):
            value = getattr(self, name).get_secret_value()
            if value == default:
                raise ValueError(f"DI_{name.upper()} is the shipped development secret; set your own for DI_ENV={self.env}")
            if len(value.encode()) < MIN_SECRET_BYTES:
                raise ValueError(f"DI_{name.upper()} must be at least {MIN_SECRET_BYTES} bytes for DI_ENV={self.env}")
        key = self.secret_key.get_secret_value()
        if not key:
            raise ValueError(f"DI_SECRET_KEY is required for DI_ENV={self.env} (it encrypts source credentials)")
        # several keys for a rotation: comma-separated, the first the current one (di.connectors.secrets)
        try:
            for k in key.split(","):
                if len(base64.urlsafe_b64decode(k.strip().encode())) != 32:
                    raise ValueError
        except ValueError:
            raise ValueError(
                "DI_SECRET_KEY must be urlsafe base64 of 32 bytes (Fernet.generate_key()), or several such keys "
                "separated by commas"
            ) from None
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
