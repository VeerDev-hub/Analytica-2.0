from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers every table on Base.metadata)
from alembic import context
from app.core.config import get_settings
from app.core.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Indexes/constraints created by hand in migration 0001 (partial, HNSW...) that the models
# don't declare. Without this, autogenerate would propose dropping them.
MANUAL = {
    "ix_column_profiles_version_position",
    "uq_dataset_versions_dataset_id_version_no",
    "ix_embedding_chunks_embedding_hnsw",
    "ix_exports_expires_at",
    "ix_jobs_user_status",
    "ix_pipeline_steps_pipeline_position",
    "ix_projects_owner_live",
}


def include_object(obj, name, type_, reflected, compare_to):
    return not (reflected and compare_to is None and name in MANUAL)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
