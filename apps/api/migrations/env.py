from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import di.models  # noqa: F401  (registers the tables on Base.metadata)
from di.config import get_settings
from di.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
# DI_DATABASE_URL, unless the caller set a URL (tests/test_models_migrations.py runs on a scratch database)
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        # compare server defaults too, so `alembic check` (tests/test_models_migrations.py) catches a default that
        # di/models.py and the migrations disagree on
        context.configure(connection=connection, target_metadata=target_metadata, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
