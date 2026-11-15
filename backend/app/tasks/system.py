"""System tasks used to verify the worker pipeline end to end."""

from app.tasks.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> str:
    return "pong"
