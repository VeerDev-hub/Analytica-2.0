import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import created_at, uuid_pk


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_column: Mapped[str | None] = mapped_column(String(255))
    # classification | regression | forecast | unsupervised
    task_type: Mapped[str | None] = mapped_column(String(32))
    # FK added by ALTER TABLE in migration 0001 (circular with pipelines).
    current_pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipelines.id", ondelete="SET NULL", use_alter=True),
    )
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    original_filename: Mapped[str | None] = mapped_column(String(255))
    original_format: Mapped[str | None] = mapped_column(String(16))  # csv xlsx xls parquet
    original_sha256: Mapped[str | None] = mapped_column(String(64))
    original_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    original_storage_key: Mapped[str | None] = mapped_column(String(1024))
    sheet_name: Mapped[str | None] = mapped_column(String(255))
    load_options: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="SET NULL", use_alter=True),
    )
    created_at: Mapped[datetime] = created_at()


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="SET NULL")
    )
    created_by_step_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_steps.id", ondelete="SET NULL", use_alter=True),
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    schema_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Dataset-level profile (duplicates, missing cells, alerts). Addition to the ER diagram.
    profile: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="building")
    created_at: Mapped[datetime] = created_at()


class ColumnProfile(Base):
    __tablename__ = "column_profiles"

    id: Mapped[uuid.UUID] = uuid_pk()
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    dtype: Mapped[str] = mapped_column(String(32), nullable=False)
    semantic_type: Mapped[str] = mapped_column(String(32), nullable=False)
    missing_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    unique_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text)
    is_private: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_target: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
