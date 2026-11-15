"""Durable job state (design 4.6). The UI reads the `jobs` table, never Celery directly.

State machine: queued -> running -> succeeded | failed | cancelled.
Progress is persisted and also published on Redis channel `job:{id}` for SSE listeners.
"""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime

import redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import session_scope
from app.models import Job

logger = logging.getLogger(__name__)
TERMINAL = ("succeeded", "failed", "cancelled")


class JobCancelled(Exception):
    pass


def create_job(
    db: Session,
    *,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    job_type: str,
    params: dict | None = None,
    step_id: uuid.UUID | None = None,
) -> Job:
    job = Job(
        project_id=project_id,
        user_id=user_id,
        job_type=job_type,
        params=params or {},
        step_id=step_id,
        status="queued",
        progress=0,
    )
    db.add(job)
    db.flush()
    return job


def enqueue(db: Session, job: Job, task, *args) -> None:
    """Commit first so the worker can see the row, then send the task."""
    db.commit()
    result = task.apply_async(args=[str(job.id), *args], task_id=str(job.id))
    if job.celery_task_id != result.id:
        job.celery_task_id = result.id
        db.commit()


def _publish(job: Job) -> None:
    try:
        client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
        client.publish(f"job:{job.id}", json.dumps(job_payload(job), default=str))
        client.close()
    except redis.RedisError:  # progress events are best-effort; the DB row is the truth
        pass


def job_payload(job: Job) -> dict:
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "result": job.result,
        "error": job.error,
    }


class JobReporter:
    """Used inside tasks to move a job through its states with short transactions."""

    def __init__(self, job_id: str | uuid.UUID):
        self.job_id = uuid.UUID(str(job_id))

    def _update(self, **fields) -> Job:
        with session_scope() as db:
            job = db.get(Job, self.job_id)
            if job is None:
                raise LookupError(f"job {self.job_id} not found")
            if job.status == "cancelled" and fields.get("status") != "cancelled":
                raise JobCancelled()
            for k, v in fields.items():
                setattr(job, k, v)
            db.flush()
            _publish(job)
            return job

    def start(self, message: str = "Starting") -> None:
        self._update(status="running", started_at=datetime.now(UTC), progress=1, message=message)

    def progress(self, pct: int, message: str | None = None) -> None:
        fields = {"progress": max(0, min(99, int(pct)))}
        if message:
            fields["message"] = message[:255]
        self._update(**fields)

    def succeed(self, result: dict | None = None, message: str = "Done") -> None:
        self._update(
            status="succeeded",
            progress=100,
            result=result or {},
            message=message,
            finished_at=datetime.now(UTC),
        )

    def fail(self, error: str) -> None:
        with contextlib.suppress(JobCancelled):
            self._update(
                status="failed", error=error[:4000], message="Failed", finished_at=datetime.now(UTC)
            )
