"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-15 18:39:18.166005

Design 2.5: extensions first, then tables in dependency order; circular FKs
(projects.current_pipeline_id, datasets.current_version_id,
dataset_versions.created_by_step_id) are added with ALTER TABLE after all tables exist.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=16), server_default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_column", sa.String(length=255), nullable=True),
        sa.Column("task_type", sa.String(length=32), nullable=True),
        sa.Column("current_pipeline_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_projects_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(op.f("ix_projects_owner_id"), "projects", ["owner_id"], unique=False)
    op.create_table(
        "recipes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], name=op.f("fk_recipes_owner_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
    )
    op.create_index(op.f("ix_recipes_owner_id"), "recipes", ["owner_id"], unique=False)
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_chat_sessions_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_chat_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
    )
    op.create_index(
        op.f("ix_chat_sessions_project_id"), "chat_sessions", ["project_id"], unique=False
    )
    op.create_table(
        "datasets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("original_format", sa.String(length=16), nullable=True),
        sa.Column("original_sha256", sa.String(length=64), nullable=True),
        sa.Column("original_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("original_storage_key", sa.String(length=1024), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column(
            "load_options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("current_version_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_datasets_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
    )
    op.create_index(op.f("ix_datasets_project_id"), "datasets", ["project_id"], unique=False)
    op.create_table(
        "recipe_steps",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("recipe_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("column_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_steps_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_steps")),
    )
    op.create_index(op.f("ix_recipe_steps_recipe_id"), "recipe_steps", ["recipe_id"], unique=False)
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("proposed_step", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            name=op.f("fk_chat_messages_session_id_chat_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    op.create_index(
        op.f("ix_chat_messages_session_id"), "chat_messages", ["session_id"], unique=False
    )
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("parent_version_id", sa.UUID(), nullable=True),
        sa.Column("created_by_step_id", sa.UUID(), nullable=True),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("schema_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_dataset_versions_dataset_id_datasets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_dataset_versions_parent_version_id_dataset_versions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_versions")),
    )
    op.create_index(
        op.f("ix_dataset_versions_dataset_id"), "dataset_versions", ["dataset_id"], unique=False
    )
    op.create_table(
        "column_profiles",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("dtype", sa.String(length=32), nullable=False),
        sa.Column("semantic_type", sa.String(length=32), nullable=False),
        sa.Column("missing_count", sa.BigInteger(), nullable=False),
        sa.Column("unique_count", sa.BigInteger(), nullable=False),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_private", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_target", sa.Boolean(), server_default="false", nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_column_profiles_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_column_profiles")),
    )
    op.create_index(
        op.f("ix_column_profiles_version_id"), "column_profiles", ["version_id"], unique=False
    )
    op.create_table(
        "dataset_splits",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("train_key", sa.String(length=1024), nullable=False),
        sa.Column("val_key", sa.String(length=1024), nullable=True),
        sa.Column("test_key", sa.String(length=1024), nullable=True),
        sa.Column("class_distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_dataset_splits_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_splits")),
    )
    op.create_index(
        op.f("ix_dataset_splits_version_id"), "dataset_splits", ["version_id"], unique=False
    )
    op.create_table(
        "embedding_chunks",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_embedding_chunks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_embedding_chunks_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_embedding_chunks")),
    )
    op.create_index(
        op.f("ix_embedding_chunks_project_id"), "embedding_chunks", ["project_id"], unique=False
    )
    op.create_table(
        "exports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_exports_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_exports_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exports")),
    )
    op.create_index(op.f("ix_exports_project_id"), "exports", ["project_id"], unique=False)
    op.create_table(
        "pipelines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("base_version_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("split_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_pipelines_base_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_pipelines_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipelines")),
    )
    op.create_index(op.f("ix_pipelines_project_id"), "pipelines", ["project_id"], unique=False)
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_reports_version_id_dataset_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index(op.f("ix_reports_version_id"), "reports", ["version_id"], unique=False)
    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pipeline_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=64), nullable=False),
        sa.Column("phase", sa.String(length=16), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("column_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input_version_id", sa.UUID(), nullable=True),
        sa.Column("output_version_id", sa.UUID(), nullable=True),
        sa.Column("fitted_state_key", sa.String(length=1024), nullable=True),
        sa.Column("rows_before", sa.BigInteger(), nullable=True),
        sa.Column("rows_after", sa.BigInteger(), nullable=True),
        sa.Column("cols_before", sa.Integer(), nullable=True),
        sa.Column("cols_after", sa.Integer(), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["input_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_pipeline_steps_input_version_id_dataset_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["output_version_id"],
            ["dataset_versions.id"],
            name=op.f("fk_pipeline_steps_output_version_id_dataset_versions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_id"],
            ["pipelines.id"],
            name=op.f("fk_pipeline_steps_pipeline_id_pipelines"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_steps")),
    )
    op.create_index(
        op.f("ix_pipeline_steps_pipeline_id"), "pipeline_steps", ["pipeline_id"], unique=False
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("step_id", sa.UUID(), nullable=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.String(length=255), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_jobs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["pipeline_steps.id"],
            name=op.f("fk_jobs_step_id_pipeline_steps"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_jobs_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_project_id"), "jobs", ["project_id"], unique=False)

    # Circular foreign keys.
    op.create_foreign_key(
        op.f("fk_projects_current_pipeline_id_pipelines"),
        "projects",
        "pipelines",
        ["current_pipeline_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_datasets_current_version_id_dataset_versions"),
        "datasets",
        "dataset_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_dataset_versions_created_by_step_id_pipeline_steps"),
        "dataset_versions",
        "pipeline_steps",
        ["created_by_step_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Indexes and constraints (design 2.3).
    op.create_unique_constraint(
        "uq_dataset_versions_dataset_id_version_no",
        "dataset_versions",
        ["dataset_id", "version_no"],
    )
    op.create_index(
        "ix_projects_owner_live",
        "projects",
        ["owner_id", "updated_at"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_pipeline_steps_pipeline_position", "pipeline_steps", ["pipeline_id", "position"]
    )
    op.create_index("ix_jobs_user_status", "jobs", ["user_id", "status"])
    op.create_index(
        "ix_column_profiles_version_position", "column_profiles", ["version_id", "position"]
    )
    op.create_index(
        "ix_exports_expires_at",
        "exports",
        ["expires_at"],
        postgresql_where=sa.text("storage_key IS NOT NULL"),
    )
    op.create_index(
        "ix_embedding_chunks_embedding_hnsw",
        "embedding_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_dataset_versions_created_by_step_id_pipeline_steps"),
        "dataset_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_datasets_current_version_id_dataset_versions"), "datasets", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_projects_current_pipeline_id_pipelines"), "projects", type_="foreignkey"
    )
    op.drop_index(op.f("ix_jobs_project_id"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_pipeline_steps_pipeline_id"), table_name="pipeline_steps")
    op.drop_table("pipeline_steps")
    op.drop_index(op.f("ix_reports_version_id"), table_name="reports")
    op.drop_table("reports")
    op.drop_index(op.f("ix_pipelines_project_id"), table_name="pipelines")
    op.drop_table("pipelines")
    op.drop_index(op.f("ix_exports_project_id"), table_name="exports")
    op.drop_table("exports")
    op.drop_index(op.f("ix_embedding_chunks_project_id"), table_name="embedding_chunks")
    op.drop_table("embedding_chunks")
    op.drop_index(op.f("ix_dataset_splits_version_id"), table_name="dataset_splits")
    op.drop_table("dataset_splits")
    op.drop_index(op.f("ix_column_profiles_version_id"), table_name="column_profiles")
    op.drop_table("column_profiles")
    op.drop_index(op.f("ix_dataset_versions_dataset_id"), table_name="dataset_versions")
    op.drop_table("dataset_versions")
    op.drop_index(op.f("ix_chat_messages_session_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index(op.f("ix_recipe_steps_recipe_id"), table_name="recipe_steps")
    op.drop_table("recipe_steps")
    op.drop_index(op.f("ix_datasets_project_id"), table_name="datasets")
    op.drop_table("datasets")
    op.drop_index(op.f("ix_chat_sessions_project_id"), table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_index(op.f("ix_recipes_owner_id"), table_name="recipes")
    op.drop_table("recipes")
    op.drop_index(op.f("ix_projects_owner_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_table("users")
