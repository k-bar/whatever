from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import settings
from app.db import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS ships its own tables (spatial_ref_sys, tiger, ...); keep autogenerate away from them.
OWN_TABLES = set(Base.metadata.tables)


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and reflected and name not in OWN_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        settings.database_url, poolclass=pool.NullPool, connect_args=settings.connect_args
    )
    with connectable.connect() as connection:
        if settings.db_schema:  # dev box: everything goes into its own schema
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{settings.db_schema}"'))
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            version_table_schema=settings.db_schema,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
