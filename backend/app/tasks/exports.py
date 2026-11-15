"""Export and baseline jobs."""

import logging
import uuid

from app.core.db import session_scope
from app.engine.readiness import baseline
from app.models import DatasetVersion, Export, Job, Project, Report
from app.services import exports as export_service
from app.services.jobs import JobCancelled, JobReporter
from app.services.versions import load_version_df
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="exports.build")
def task_export(job_id: str) -> None:
    rep = JobReporter(job_id)
    try:
        rep.start("Preparing export")
        with session_scope() as db:
            job = db.get(Job, uuid.UUID(job_id))
            export = db.get(Export, uuid.UUID(job.params["export_id"]))
            version = db.get(DatasetVersion, export.version_id)
            project = db.get(Project, export.project_id)
            df = load_version_df(version)
            rep.progress(40, f"Writing {export.kind} ({export.format})")
            export_service.finish(db, export, project, version, df)
            result = {"export_id": str(export.id), "storage_key": export.storage_key}
        rep.succeed(result, "Export ready")
    except JobCancelled:
        pass
    except Exception as e:  # noqa: BLE001
        logger.exception("export failed")
        with session_scope() as db:
            job = db.get(Job, uuid.UUID(job_id))
            export = db.get(Export, uuid.UUID(job.params["export_id"]))
            export.status = "failed"
        rep.fail(f"{e}")


@celery_app.task(name="readiness.baseline")
def task_baseline(job_id: str) -> None:
    rep = JobReporter(job_id)
    try:
        rep.start("Training baseline models")
        with session_scope() as db:
            job = db.get(Job, uuid.UUID(job_id))
            version = db.get(DatasetVersion, uuid.UUID(job.params["version_id"]))
            project = db.get(Project, job.project_id)
            target, task_type, version_id = (project.target_column, project.task_type, version.id)
            df = load_version_df(version)
        rep.progress(30, "Fitting models on train rows")
        result = baseline(df, target, task_type)
        with session_scope() as db:
            db.add(Report(version_id=version_id, kind="baseline", status="ready", summary=result))
        rep.succeed(result, "Baseline ready")
    except JobCancelled:
        pass
    except ValueError as e:
        rep.fail(str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("baseline failed")
        rep.fail(f"{type(e).__name__}: {e}")
