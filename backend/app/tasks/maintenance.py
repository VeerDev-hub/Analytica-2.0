"""Housekeeping tasks: purge deleted projects (design 1.7) and expired exports."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import session_scope
from app.models import Export, Project
from app.storage.backend import get_storage, project_prefix
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="maintenance.purge_project")
def task_purge_project(project_id: str) -> int:
    with session_scope() as db:
        p = db.get(Project, uuid.UUID(project_id))
        if p is None or p.deleted_at is None:
            return 0
        n = get_storage().delete_prefix(project_prefix(p.owner_id, p.id))
        db.delete(p)  # cascades to datasets, versions, pipelines, jobs, chat, embeddings
    logger.info("purged project %s (%d objects)", project_id, n)
    return n


@celery_app.task(name="maintenance.purge_deleted_projects")
def task_purge_deleted_projects() -> int:
    with session_scope() as db:
        ids = [
            str(i) for i in db.scalars(select(Project.id).where(Project.deleted_at.is_not(None)))
        ]
    for pid in ids:
        task_purge_project(pid)
    return len(ids)


@celery_app.task(name="maintenance.expire_exports")
def task_expire_exports() -> int:
    now = datetime.now(UTC)
    with session_scope() as db:
        expired = list(
            db.scalars(
                select(Export).where(Export.expires_at < now, Export.storage_key.is_not(None))
            )
        )
        for e in expired:
            get_storage().delete_prefix(e.storage_key)
            e.storage_key = None
            e.status = "expired"
    return len(expired)
