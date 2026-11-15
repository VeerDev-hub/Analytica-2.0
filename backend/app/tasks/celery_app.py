"""Celery application. Workers start with: celery -A app.tasks.celery_app worker"""

from celery import Celery
from celery.signals import setup_logging

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

TASK_MODULES = [
    "app.tasks.system",
    "app.tasks.ingest",
    "app.tasks.maintenance",
    "app.tasks.pipeline",
    "app.tasks.exports",
]

celery_app = Celery(
    "analytica",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=TASK_MODULES,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,  # re-run a task if the worker dies mid-job
    worker_prefetch_multiplier=1,  # data jobs are heavy; take one at a time
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    task_always_eager=settings.celery_eager,
    task_eager_propagates=settings.celery_eager,
    beat_schedule={
        "purge-deleted-projects": {
            "task": "maintenance.purge_deleted_projects",
            "schedule": 3600.0,
        },
        "expire-exports": {"task": "maintenance.expire_exports", "schedule": 3600.0},
    },
)


@setup_logging.connect
def _configure_worker_logging(**_kwargs) -> None:
    configure_logging(settings.log_level)
