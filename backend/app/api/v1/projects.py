import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Response
from sqlalchemy import func, select

from app.api.deps import DB, CurrentUser
from app.core.errors import ValidationFailed
from app.models import ColumnProfile, Dataset, DatasetVersion, Project
from app.repositories.access import get_project, primary_dataset
from app.schemas.common import (
    DatasetOut,
    ProjectDetailOut,
    ProjectIn,
    ProjectListOut,
    ProjectOut,
    ProjectPatch,
    VersionOut,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def dataset_out(db, ds: Dataset | None) -> DatasetOut | None:
    if ds is None:
        return None
    out = DatasetOut.model_validate(ds)
    if ds.current_version_id:
        v = db.get(DatasetVersion, ds.current_version_id)
        out.current_version = VersionOut.model_validate(v) if v else None
    return out


@router.get("", response_model=list[ProjectListOut])
def list_projects(user: CurrentUser, db: DB) -> list[ProjectListOut]:
    from app.models import PipelineStep

    projects = list(
        db.scalars(
            select(Project)
            .where(Project.owner_id == user.id, Project.deleted_at.is_(None))
            .order_by(Project.updated_at.desc())
        )
    )
    out = []
    for p in projects:
        row = ProjectListOut.model_validate(p)
        ds = primary_dataset(db, p)
        if ds:
            row.dataset_name = ds.original_filename
            v = db.get(DatasetVersion, ds.current_version_id) if ds.current_version_id else None
            if v:
                row.rows, row.columns, row.version_no = v.row_count, v.column_count, v.version_no
        if p.current_pipeline_id:
            row.steps = int(
                db.scalar(
                    select(func.count())
                    .select_from(PipelineStep)
                    .where(
                        PipelineStep.pipeline_id == p.current_pipeline_id,
                        PipelineStep.status == "applied",
                    )
                )
                or 0
            )
        out.append(row)
    return out


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, user: CurrentUser, db: DB) -> Project:
    p = Project(owner_id=user.id, name=body.name.strip(), description=body.description)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project_detail(project_id: uuid.UUID, user: CurrentUser, db: DB) -> ProjectDetailOut:
    p = get_project(db, user, project_id)
    out = ProjectDetailOut.model_validate(p)
    out.dataset = dataset_out(db, primary_dataset(db, p))
    return out


@router.patch("/{project_id}", response_model=ProjectOut)
def patch_project(project_id: uuid.UUID, body: ProjectPatch, user: CurrentUser, db: DB) -> Project:
    p = get_project(db, user, project_id)
    fields = body.model_dump(exclude_unset=True)
    if "target_column" in fields:
        target = fields["target_column"]
        ds = primary_dataset(db, p)
        if target is not None:
            if ds is None or ds.current_version_id is None:
                raise ValidationFailed("Upload a dataset before choosing a target column")
            names = {
                c
                for c in db.scalars(
                    select(ColumnProfile.name).where(
                        ColumnProfile.version_id == ds.current_version_id
                    )
                )
            }
            if target not in names:
                raise ValidationFailed(f"Column '{target}' is not in the current dataset")
        if ds and ds.current_version_id:
            for col in db.scalars(
                select(ColumnProfile).where(ColumnProfile.version_id == ds.current_version_id)
            ):
                col.is_target = col.name == target
    for k, v in fields.items():
        setattr(p, k, v.strip() if isinstance(v, str) and k == "name" else v)
    p.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    """Soft delete now; a worker purges S3 objects and rows (design 1.7: within 24 h)."""
    p = get_project(db, user, project_id)
    p.deleted_at = datetime.now(UTC)
    db.commit()
    from app.tasks.maintenance import task_purge_project

    task_purge_project.delay(str(p.id))
    return Response(status_code=204)


@router.post("/{project_id}/free-space")
def free_space(project_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    """Delete dataset versions no step needs any more (undone or replaced ones)."""
    from app.services.quota import free_unused_versions

    p = get_project(db, user, project_id)
    if p.current_pipeline_id:
        from app.models import Pipeline
        from app.services.pipeline import ensure_idle

        ensure_idle(db, db.get(Pipeline, p.current_pipeline_id))
    return free_unused_versions(db, p)
