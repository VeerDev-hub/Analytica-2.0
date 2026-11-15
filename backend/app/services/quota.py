"""Per-account storage limits (default 5 GB, admin-adjustable).

Counted: original uploads, every dataset version (each cleaning step writes one) and
exports that have not expired. Deleted projects stop counting immediately.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Dataset,
    DatasetSplit,
    DatasetVersion,
    Export,
    Pipeline,
    PipelineStep,
    Project,
    User,
)
from app.services import app_settings
from app.storage.backend import get_storage

MB = 1024 * 1024


class QuotaExceeded(AppError):
    status_code = 413
    code = "STORAGE_QUOTA_EXCEEDED"


def quota_bytes(db: Session, user: User) -> int:
    mb = user.storage_quota_mb or int(app_settings.get(db, "storage_quota_mb"))
    return int(mb) * MB


def _live_projects(user_id: uuid.UUID):
    return select(Project.id).where(Project.owner_id == user_id, Project.deleted_at.is_(None))


def usage_by_project(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    live = _live_projects(user_id)
    out: dict[uuid.UUID, int] = {}
    for pid, n in db.execute(
        select(Dataset.project_id, func.coalesce(func.sum(Dataset.original_size_bytes), 0))
        .where(Dataset.project_id.in_(live))
        .group_by(Dataset.project_id)
    ):
        out[pid] = out.get(pid, 0) + int(n)
    for pid, n in db.execute(
        select(Dataset.project_id, func.coalesce(func.sum(DatasetVersion.size_bytes), 0))
        .join(DatasetVersion, DatasetVersion.dataset_id == Dataset.id)
        .where(Dataset.project_id.in_(live))
        .group_by(Dataset.project_id)
    ):
        out[pid] = out.get(pid, 0) + int(n)
    for pid, n in db.execute(
        select(Export.project_id, func.coalesce(func.sum(Export.size_bytes), 0))
        .where(Export.project_id.in_(live), Export.storage_key.is_not(None))
        .group_by(Export.project_id)
    ):
        out[pid] = out.get(pid, 0) + int(n)
    return out


def usage_bytes(db: Session, user_id: uuid.UUID) -> int:
    return sum(usage_by_project(db, user_id).values())


def summary(db: Session, user: User) -> dict:
    used, limit = usage_bytes(db, user.id), quota_bytes(db, user)
    return {
        "used_bytes": used,
        "quota_bytes": limit,
        "percent": round(100 * used / limit, 1) if limit else 0.0,
        "custom_quota": user.storage_quota_mb is not None,
    }


def _human(n: int) -> str:
    return f"{n / 1024**3:.2f} GB" if n >= 1024**3 else f"{n / MB:.0f} MB"


def ensure_room(db: Session, user: User, extra_bytes: int = 0) -> None:
    """Refuse work that would push the account over its limit."""
    used, limit = usage_bytes(db, user.id), quota_bytes(db, user)
    if used + extra_bytes > limit or (extra_bytes == 0 and used >= limit):
        need = f" This file needs {_human(extra_bytes)}." if extra_bytes else ""
        raise QuotaExceeded(
            f"Storage limit reached: you are using {_human(used)} of {_human(limit)}.{need} "
            "Delete a project or use “Free up space” in Account → Storage.",
            details={"used_bytes": used, "quota_bytes": limit, "extra_bytes": extra_bytes},
        )


def free_unused_versions(db: Session, project: Project) -> dict:
    """Delete dataset versions nothing points to any more (undone branches, replaced
    replays). Keeps the original, the current version, every applied step's input/output
    and versions with live exports. Undone/failed steps are removed (redo is lost)."""
    ds = db.scalars(select(Dataset).where(Dataset.project_id == project.id)).first()
    if ds is None:
        return {"deleted_versions": 0, "freed_bytes": 0}
    keep: set[uuid.UUID] = {v for v in (ds.current_version_id,) if v}
    pl = db.get(Pipeline, project.current_pipeline_id) if project.current_pipeline_id else None
    if pl:
        keep.add(pl.base_version_id)
        for st in db.scalars(select(PipelineStep).where(PipelineStep.pipeline_id == pl.id)):
            if st.status in ("applied", "pending", "running"):
                keep.update(v for v in (st.input_version_id, st.output_version_id) if v)
            else:
                db.delete(st)
    keep.update(
        db.scalars(
            select(Export.version_id).where(
                Export.project_id == project.id, Export.storage_key.is_not(None)
            )
        )
    )
    storage = get_storage()
    freed = deleted = 0
    for v in db.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id == ds.id)):
        if v.id in keep:
            continue
        for sp in db.scalars(select(DatasetSplit).where(DatasetSplit.version_id == v.id)):
            for key in (sp.train_key, sp.val_key, sp.test_key):
                if key:
                    storage.delete_prefix(key)
        storage.delete_prefix(v.storage_key)
        freed += v.size_bytes or 0
        deleted += 1
        db.delete(v)
    db.commit()
    return {"deleted_versions": deleted, "freed_bytes": freed}
