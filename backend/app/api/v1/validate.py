import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.errors import AppError, ValidationFailed
from app.engine.readiness import check
from app.models import Export
from app.repositories.access import get_export, get_project
from app.schemas.common import ORM
from app.services import jobs as job_service
from app.services.exports import KINDS
from app.services.pipeline import current_version
from app.services.versions import load_version_df
from app.storage.backend import get_storage

router = APIRouter(tags=["validate"])


class ExportIn(BaseModel):
    kind: str
    format: str | None = None


class ExportOut(ORM):
    id: uuid.UUID
    version_id: uuid.UUID
    kind: str
    format: str
    status: str
    created_at: datetime
    expires_at: datetime | None


class ExportCreated(BaseModel):
    export: ExportOut
    job_id: uuid.UUID


@router.get("/projects/{project_id}/readiness")
def readiness(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    framework: str = Query("sklearn", pattern="^(sklearn|xgboost|pytorch|tensorflow)$"),
) -> dict:
    project = get_project(db, user, project_id)
    v = current_version(db, project)
    out = check(load_version_df(v), project.target_column, project.task_type, framework)
    out["version_id"] = str(v.id)
    return out


@router.post("/projects/{project_id}/baseline", status_code=202)
def run_baseline(project_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    project = get_project(db, user, project_id)
    if not project.target_column:
        raise ValidationFailed("Choose a target column first", code="NO_TARGET")
    v = current_version(db, project)
    job = job_service.create_job(
        db,
        project_id=project.id,
        user_id=user.id,
        job_type="baseline",
        params={"version_id": str(v.id)},
    )
    from app.tasks.exports import task_baseline

    job_service.enqueue(db, job, task_baseline)
    return {"job_id": str(job.id)}


@router.get("/projects/{project_id}/exports", response_model=list[ExportOut])
def list_exports(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[Export]:
    project = get_project(db, user, project_id)
    return list(
        db.scalars(
            select(Export)
            .where(Export.project_id == project.id)
            .order_by(Export.created_at.desc())
            .limit(50)
        )
    )


@router.post("/projects/{project_id}/exports", response_model=ExportCreated, status_code=202)
def create_export(
    project_id: uuid.UUID, body: ExportIn, user: CurrentUser, db: DB
) -> ExportCreated:
    project = get_project(db, user, project_id)
    if body.kind not in KINDS:
        raise ValidationFailed(f"kind must be one of {sorted(KINDS)}")
    fmt = body.format or KINDS[body.kind][0]
    if fmt not in KINDS[body.kind]:
        raise ValidationFailed(f"format for {body.kind} must be one of {KINDS[body.kind]}")
    from app.services.quota import ensure_room

    ensure_room(db, user)
    v = current_version(db, project)
    export = Export(
        project_id=project.id, version_id=v.id, kind=body.kind, format=fmt, status="pending"
    )
    db.add(export)
    db.flush()
    job = job_service.create_job(
        db,
        project_id=project.id,
        user_id=user.id,
        job_type="export",
        params={"export_id": str(export.id)},
    )
    from app.tasks.exports import task_export

    job_service.enqueue(db, job, task_export)
    db.refresh(export)
    return ExportCreated(export=ExportOut.model_validate(export), job_id=job.id)


@router.get("/exports/{export_id}/download")
def download(export_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    """Streams the file through the API (works with any storage backend and keeps the
    bucket private). Large-file deployments can switch to short-lived presigned URLs."""
    export, _ = get_export(db, user, export_id)
    if export.status != "ready" or not export.storage_key:
        raise AppError("Export is not ready", code="EXPORT_NOT_READY", status_code=409)
    if export.expires_at and export.expires_at < datetime.now(UTC):
        raise AppError(
            "Export has expired; create it again", code="EXPORT_EXPIRED", status_code=410
        )
    filename = export.storage_key.rsplit("/", 1)[-1]
    data = get_storage().get_bytes(export.storage_key)
    return Response(
        data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
