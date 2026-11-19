from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DI_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://circ:circ@localhost:5432/di"
    source_sim_url: str = "http://localhost:8100"
    worker_poll_seconds: float = 1.0
    job_max_attempts: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
