"""Create immutable dataset versions (rule 1): write Parquet, profile, store metadata."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.engine.profiling import profile as profile_df
from app.engine.profiling import schema_snapshot
from app.models import ColumnProfile, Dataset, DatasetVersion, Project
from app.storage.backend import get_storage, project_prefix
from app.storage.cache import local_path


def version_key(project: Project, dataset: Dataset, version_no: int) -> str:
    return (
        f"{project_prefix(project.owner_id, project.id)}datasets/{dataset.id}/v{version_no}.parquet"
    )


def write_parquet(df: pd.DataFrame, key: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "data.parquet"
        df.to_parquet(path, index=False, compression="zstd")
        return get_storage().put_file(key, path, "application/vnd.apache.parquet")


def create_version(
    db: Session,
    *,
    project: Project,
    dataset: Dataset,
    df: pd.DataFrame,
    parent: DatasetVersion | None,
    step_id: uuid.UUID | None = None,
    load_notes: list[str] | None = None,
    carry_columns_from: DatasetVersion | None = None,
) -> DatasetVersion:
    """Write `df` as the next version of `dataset` and profile it. Does not move the pointer."""
    next_no = (
        db.scalar(
            select(func.max(DatasetVersion.version_no)).where(
                DatasetVersion.dataset_id == dataset.id
            )
        )
        or 0
    ) + 1
    key = version_key(project, dataset, next_no)
    size = write_parquet(df, key)
    prof = profile_df(df, target=project.target_column)
    if load_notes:
        prof["load_notes"] = load_notes

    version = DatasetVersion(
        dataset_id=dataset.id,
        parent_version_id=parent.id if parent else None,
        created_by_step_id=step_id,
        version_no=next_no,
        storage_key=key,
        row_count=int(df.shape[0]),
        column_count=int(df.shape[1]),
        size_bytes=size,
        schema_snapshot=schema_snapshot(prof),
        profile={k: v for k, v in prof.items() if k != "columns"},
        status="ready",
    )
    db.add(version)
    db.flush()

    # User-written metadata (descriptions, private/target flags) follows the column forward.
    carried: dict[str, ColumnProfile] = {}
    if carry_columns_from is not None:
        carried = {
            c.name: c
            for c in db.scalars(
                select(ColumnProfile).where(ColumnProfile.version_id == carry_columns_from.id)
            )
        }
    for col in prof["columns"]:
        prev = carried.get(col["name"])
        db.add(
            ColumnProfile(
                version_id=version.id,
                name=col["name"],
                position=col["position"],
                dtype=col["dtype"][:32],
                semantic_type=col["semantic_type"],
                missing_count=col["missing_count"],
                unique_count=col["unique_count"],
                stats=col["stats"],
                description=prev.description if prev else None,
                is_private=prev.is_private if prev else False,
                is_target=(col["name"] == project.target_column),
            )
        )
    db.flush()
    return version


def load_version_df(version: DatasetVersion, columns: list[str] | None = None) -> pd.DataFrame:
    return pd.read_parquet(local_path(version.storage_key), columns=columns)


def sample_version_df(version: DatasetVersion, n: int, seed: int = 0) -> pd.DataFrame:
    df = load_version_df(version)
    return df if len(df) <= n else df.sample(n=n, random_state=seed).sort_index()
