"""Owner-scoped lookups (design rule 7). Every route resolves resources through these so a
user can never reach another user's rows; missing and forbidden both return 404."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models import (
    ChatSession,
    ColumnProfile,
    Dataset,
    DatasetVersion,
    Export,
    Job,
    Pipeline,
    PipelineStep,
    Project,
    User,
)


def get_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.owner_id != user.id or p.deleted_at is not None:
        raise NotFound("Project not found")
    return p


def get_dataset(db: Session, user: User, dataset_id: uuid.UUID) -> tuple[Dataset, Project]:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFound("Dataset not found")
    return ds, get_project(db, user, ds.project_id)


def get_version(
    db: Session, user: User, version_id: uuid.UUID
) -> tuple[DatasetVersion, Dataset, Project]:
    v = db.get(DatasetVersion, version_id)
    if v is None:
        raise NotFound("Version not found")
    ds, p = get_dataset(db, user, v.dataset_id)
    return v, ds, p


def get_column(db: Session, user: User, column_id: uuid.UUID) -> ColumnProfile:
    c = db.get(ColumnProfile, column_id)
    if c is None:
        raise NotFound("Column not found")
    get_version(db, user, c.version_id)
    return c


def get_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    j = db.get(Job, job_id)
    if j is None or j.user_id != user.id:
        raise NotFound("Job not found")
    return j


def get_pipeline(db: Session, user: User, pipeline_id: uuid.UUID) -> tuple[Pipeline, Project]:
    pl = db.get(Pipeline, pipeline_id)
    if pl is None:
        raise NotFound("Pipeline not found")
    return pl, get_project(db, user, pl.project_id)


def get_step(db: Session, user: User, step_id: uuid.UUID) -> tuple[PipelineStep, Pipeline, Project]:
    st = db.get(PipelineStep, step_id)
    if st is None:
        raise NotFound("Step not found")
    pl, p = get_pipeline(db, user, st.pipeline_id)
    return st, pl, p


def get_export(db: Session, user: User, export_id: uuid.UUID) -> tuple[Export, Project]:
    e = db.get(Export, export_id)
    if e is None:
        raise NotFound("Export not found")
    return e, get_project(db, user, e.project_id)


def get_chat_session(db: Session, user: User, session_id: uuid.UUID) -> tuple[ChatSession, Project]:
    s = db.get(ChatSession, session_id)
    if s is None or s.user_id != user.id:
        raise NotFound("Chat session not found")
    return s, get_project(db, user, s.project_id)


def primary_dataset(db: Session, project: Project) -> Dataset | None:
    return db.scalars(
        select(Dataset).where(Dataset.project_id == project.id).order_by(Dataset.created_at)
    ).first()
