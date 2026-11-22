from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SIM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://circ:circ@localhost:5432/sources"
    # B1 golden files: the seed (docs/backend-steps.md, B2). Mounted at /fixtures in Docker.
    golden_dir: str = "/fixtures/golden"
    # B6: run the scheduler and webhook sender in the background (tests switch this off and call them directly)
    background: bool = True
    # B6: start with the demo's faults (Ritchie Bros. token expired); off by default so contract tests see a healthy system
    demo_faults: bool = False
    # S/4HANA mock credentials (demo values): "user:password,…" for Basic auth, "client:secret,…" for OAuth
    s4_users: str = "DI_CONNECTOR:Circularity-demo-1"
    s4_clients: str = "di-connector:circularity-demo-secret"
    # SAP Ariba mock (demo values): application key, OAuth client "id:secret", realm
    ariba_api_key: str = "circularity-demo-ariba-key"
    ariba_client: str = "di-connector:circularity-demo-ariba-secret"
    ariba_realm: str = "northfield-T"


@lru_cache
def get_settings() -> Settings:
    return Settings()
