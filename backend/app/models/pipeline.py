import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import created_at, uuid_pk


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    base_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, default="Main")
    # {"ratios": [0.7, 0.15, 0.15], "seed": 42, "stratify_by": "y", "group_by": null, ...}
    split_config: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = created_at()


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id: Mapped[uuid.UUID] = uuid_pk()
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)  # pre_split | post_split
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    column_scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # pending | running | applied | failed | undone
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    input_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="SET NULL")
    )
    output_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="SET NULL")
    )
    fitted_state_key: Mapped[str | None] = mapped_column(String(1024))
    rows_before: Mapped[int | None] = mapped_column(BigInteger)
    rows_after: Mapped[int | None] = mapped_column(BigInteger)
    cols_before: Mapped[int | None] = mapped_column(Integer)
    cols_after: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = created_at()


class RecipeStep(Base):
    __tablename__ = "recipe_steps"

    id: Mapped[uuid.UUID] = uuid_pk()
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    column_scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class DatasetSplit(Base):
    __tablename__ = "dataset_splits"

    id: Mapped[uuid.UUID] = uuid_pk()
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    train_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    val_key: Mapped[str | None] = mapped_column(String(1024))
    test_key: Mapped[str | None] = mapped_column(String(1024))
    class_distribution: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()
