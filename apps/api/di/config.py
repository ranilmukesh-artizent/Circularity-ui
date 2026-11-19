from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DI_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://circ:circ@localhost:5432/di"
    source_sim_url: str = "http://localhost:8100"
    worker_poll_seconds: float = 1.0
    job_max_attempts: int = 5
    # B1 golden files: the access policy and reference data (mounted at /fixtures in Docker)
    golden_dir: str = "/fixtures/golden"
    # B7: sign-in tokens (HS256). Override DI_JWT_SECRET outside local development.
    jwt_secret: str = "dev-only-change-me-circularity-di-api-secret"
    jwt_ttl_minutes: int = 720
    # B9: where source-sim delivers change events, and the shared signing secret
    webhook_url: str = "http://api:8000/api/webhooks/source-sim"
    webhook_secret: str = "dev-only-source-sim-webhook-secret"
    # B13b: what "now" is (di/clock.py): "pinned" to the demo's as-of time, or "sim" = source-sim's simulated clock
    clock: str = "pinned"
    clock_cache_seconds: float = 2.0  # how long the simulated clock's anchor is reused before it is read again
    # B13b: send approved decisions' steps to the systems (di/instructions); off unless the services turn it on
    instructions: bool = False
    # a step with no matching write in the mocks is acknowledged by a simulated adapter after this many simulated hours
    simulated_ack_hours: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
