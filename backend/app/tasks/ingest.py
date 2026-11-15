"""Ingest an uploaded file into dataset version 1, then profile it (design 4.2)."""

import logging
import tempfile
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.db import session_scope
from app.engine.loaders import LoadError, load_file
from app.models import Dataset, Pipeline, Project
from app.services.jobs import JobCancelled, JobReporter
from app.services.versions import create_version
from app.storage.backend import get_storage
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="datasets.ingest")
def task_ingest(job_id: str) -> None:
    rep = JobReporter(job_id)
    try:
        rep.start("Reading file")
        with session_scope() as db:
            from app.models import Job

            job = db.get(Job, uuid.UUID(job_id))
            dataset = db.get(Dataset, uuid.UUID(job.params["dataset_id"]))
            raw_key, fmt, options = (
                dataset.original_storage_key,
                dataset.original_format,
                dict(dataset.load_options or {}),
            )

        with tempfile.TemporaryDirectory() as tmp:
            local = get_storage().download(raw_key, Path(tmp) / f"raw.{fmt}")
            rep.progress(20, "Detecting encoding, delimiter and types")
            loaded = load_file(local, fmt, options)

        df = loaded.df
        if len(df) > get_settings().max_rows:
            raise LoadError(
                f"The file has {len(df):,} rows; the limit is {get_settings().max_rows:,}."
            )
        rep.progress(55, f"Loaded {len(df):,} rows × {df.shape[1]} columns; profiling")

        with session_scope() as db:
            dataset = db.get(Dataset, dataset.id)
            project = db.get(Project, dataset.project_id)
            dataset.load_options = {**options, **loaded.options}
            if loaded.options.get("sheet_name"):
                dataset.sheet_name = loaded.options["sheet_name"]
            version = create_version(
                db, project=project, dataset=dataset, df=df, parent=None, load_notes=loaded.notes
            )
            dataset.current_version_id = version.id
            pipeline = Pipeline(project_id=project.id, base_version_id=version.id, name="Main")
            db.add(pipeline)
            db.flush()
            project.current_pipeline_id = pipeline.id
            result = {
                "dataset_id": str(dataset.id),
                "version_id": str(version.id),
                "rows": version.row_count,
                "columns": version.column_count,
            }
        rep.succeed(result, f"Ready: {result['rows']:,} rows")
    except JobCancelled:
        logger.info("ingest %s cancelled", job_id)
    except LoadError as exc:
        rep.fail(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest failed")
        rep.fail(f"Unexpected error while loading the file: {type(exc).__name__}: {exc}")
