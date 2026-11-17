import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL before running Alembic")
    return url.replace("+aiosqlite", "")  # psycopg works in sync mode as-is


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
