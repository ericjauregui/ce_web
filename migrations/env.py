from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import text

from domains.orders import Base, create_database_engine, database_url_from_env


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url_from_env(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_database_engine(database_url_from_env())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET LOCAL lock_timeout = '10s'"))
                connection.execute(text("SELECT pg_advisory_xact_lock(736924153)"))
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
