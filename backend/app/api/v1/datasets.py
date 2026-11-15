import json
import uuid

from fastapi import APIRouter, File, Form, Query, UploadFile
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.api.v1.projects import dataset_out
from app.core.errors import Conflict, ValidationFailed
from app.models import ColumnProfile, Dataset, DatasetVersion
from app.repositories.access import get_column, get_dataset, get_project, get_version
from app.schemas.common import (
    ColumnOut,
    ColumnPatch,
    DatasetOut,
    OverviewOut,
    RowsOut,
    SetCurrentIn,
    UploadOut,
    VersionOut,
)
from app.services import datasets as dataset_service
from app.services.rows import query_rows

router = APIRouter(tags=["datasets"])


@router.post("/projects/{project_id}/datasets", response_model=UploadOut, status_code=202)
def upload(
    project_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    file: UploadFile = File(...),
    options: str | None = Form(default=None),
) -> UploadOut:
    project = get_project(db, user, project_id)
    try:
        opts = json.loads(options) if options else {}
        assert isinstance(opts, dict)
    except (ValueError, AssertionError) as exc:
        raise ValidationFailed("options must be a JSON object") from exc
    allowed = {"encoding", "delimiter", "header_row", "sheet_name"}
    opts = {k: v for k, v in opts.items() if k in allowed and v not in (None, "")}

    # v1: one dataset per project. A failed earlier upload is replaced.
    for existing in db.scalars(select(Dataset).where(Dataset.project_id == project.id)):
        if existing.current_version_id is not None:
            raise Conflict(
                "This project already has a dataset. Create a new project for another file.",
                code="DATASET_EXISTS",
            )
        db.delete(existing)
    db.flush()
    dataset, job_id = dataset_service.upload_dataset(db, user, project, file, opts)
    db.refresh(dataset)
    return UploadOut(dataset=DatasetOut.model_validate(dataset), job_id=job_id)


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset_detail(dataset_id: uuid.UUID, user: CurrentUser, db: DB) -> DatasetOut:
    ds, _ = get_dataset(db, user, dataset_id)
    return dataset_out(db, ds)


@router.get("/datasets/{dataset_id}/versions", response_model=list[VersionOut])
def list_versions(dataset_id: uuid.UUID, user: CurrentUser, db: DB) -> list[DatasetVersion]:
    ds, _ = get_dataset(db, user, dataset_id)
    return list(
        db.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == ds.id)
            .order_by(DatasetVersion.version_no)
        )
    )


@router.post("/datasets/{dataset_id}/current", response_model=DatasetOut)
def set_current(dataset_id: uuid.UUID, body: SetCurrentIn, user: CurrentUser, db: DB) -> DatasetOut:
    """Move the current-version pointer (low-level undo/redo; the pipeline API wraps this)."""
    ds, _ = get_dataset(db, user, dataset_id)
    v = db.get(DatasetVersion, body.version_id)
    if v is None or v.dataset_id != ds.id or v.status != "ready":
        raise ValidationFailed("Version does not belong to this dataset")
    ds.current_version_id = v.id
    db.commit()
    return dataset_out(db, ds)


@router.get("/versions/{version_id}/rows", response_model=RowsOut)
def rows(
    version_id: uuid.UUID,
    user: CurrentUser,
    db: DB,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sort: str | None = Query(None, description="column:asc|desc"),
    filter: str | None = Query(None, description='JSON [{"column","op","value"}]'),
) -> dict:
    v, _, _ = get_version(db, user, version_id)
    return query_rows(v, offset, limit, sort, filter)


@router.get("/versions/{version_id}/columns", response_model=list[ColumnOut])
def columns(version_id: uuid.UUID, user: CurrentUser, db: DB) -> list[ColumnProfile]:
    v, _, _ = get_version(db, user, version_id)
    return list(
        db.scalars(
            select(ColumnProfile)
            .where(ColumnProfile.version_id == v.id)
            .order_by(ColumnProfile.position)
        )
    )


@router.patch("/columns/{column_id}", response_model=ColumnOut)
def patch_column(
    column_id: uuid.UUID, body: ColumnPatch, user: CurrentUser, db: DB
) -> ColumnProfile:
    col = get_column(db, user, column_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "is_target":
            continue  # target is a project setting: PATCH /projects/{id} target_column
        setattr(col, k, v)
    db.commit()
    db.refresh(col)
    return col


@router.get("/versions/{version_id}/overview", response_model=OverviewOut)
def overview(version_id: uuid.UUID, user: CurrentUser, db: DB) -> OverviewOut:
    v, _, _ = get_version(db, user, version_id)
    cols = list(
        db.scalars(
            select(ColumnProfile)
            .where(ColumnProfile.version_id == v.id)
            .order_by(ColumnProfile.position)
        )
    )
    prof = v.profile or {}
    return OverviewOut(
        version=VersionOut.model_validate(v),
        summary=prof.get("summary", {}),
        alerts=prof.get("alerts", []),
        load_notes=prof.get("load_notes", []),
        columns=[ColumnOut.model_validate(c) for c in cols],
    )
