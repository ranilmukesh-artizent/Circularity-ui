from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://circ:circ@localhost:5432/sources"
    # B1 golden files: the seed (docs/BACKEND_STEPS.md, B2). Mounted at /fixtures in Docker.
    golden_dir: str = "/fixtures/golden"


@lru_cache
def get_settings() -> Settings:
    return Settings()
