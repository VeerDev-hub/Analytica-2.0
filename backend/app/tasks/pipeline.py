"""Run one or more pipeline steps in order, each producing a new immutable version (4.3)."""

import logging
import uuid
from datetime import UTC, datetime

from app.core.db import session_scope
from app.engine.pipeline import StepSpec, run_step
from app.engine.transforms import StepError
from app.engine.transforms.base import jsonable_state, state_to_bytes
from app.models import Dataset, DatasetVersion, Job, Pipeline, PipelineStep, Project
from app.services.jobs import JobCancelled, JobReporter
from app.services.versions import create_version, load_version_df
from app.storage.backend import get_storage, project_prefix
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="pipeline.run_steps")
def task_run_steps(job_id: str) -> None:
    rep = JobReporter(job_id)
    with session_scope() as db:
        job = db.get(Job, uuid.UUID(job_id))
        step_ids = [uuid.UUID(s) for s in job.params["step_ids"]]
        pipeline = db.get(Pipeline, uuid.UUID(job.params["pipeline_id"]))
        project = db.get(Project, pipeline.project_id)
        project_id, pipeline_id = project.id, pipeline.id
    total = len(step_ids)
    done: list[str] = []
    try:
        rep.start(f"Running {total} step{'s' if total > 1 else ''}")
        prev_output: uuid.UUID | None = None
        for i, step_id in enumerate(step_ids):
            with session_scope() as db:
                step = db.get(PipelineStep, step_id)
                project = db.get(Project, project_id)
                if prev_output is not None:
                    step.input_version_id = prev_output
                input_v = db.get(DatasetVersion, step.input_version_id)
                dataset = db.get(Dataset, input_v.dataset_id)
                step.status = "running"
                label = step.step_type.replace("_", " ")
                spec = StepSpec(step.step_type, step.params or {}, step.is_enabled, str(step.id))
                target, task_type = project.target_column, project.task_type
            rep.progress(5 + int(90 * i / total), f"Step {i + 1}/{total}: {label}")

            if not spec.is_enabled:  # disabled: pass the input through unchanged
                with session_scope() as db:
                    step = db.get(PipelineStep, step_id)
                    step.output_version_id = step.input_version_id
                    step.status = "applied"
                    step.rows_before = step.rows_after = input_v.row_count
                    step.cols_before = step.cols_after = input_v.column_count
                    prev_output = step.output_version_id
                done.append(str(step_id))
                continue

            df = load_version_df(input_v)
            try:
                res = run_step(spec, df, target=target, task_type=task_type)
            except StepError as e:
                raise _StepFailed(step_id, str(e)) from e
            except (ValueError, TypeError, KeyError, MemoryError) as e:
                raise _StepFailed(step_id, f"{type(e).__name__}: {e}") from e

            with session_scope() as db:
                step = db.get(PipelineStep, step_id)
                project = db.get(Project, project_id)
                dataset = db.get(Dataset, dataset.id)
                input_v = db.get(DatasetVersion, step.input_version_id)
                if step.step_type == "rename_columns" and project.target_column in (
                    step.params.get("mapping") or {}
                ):
                    project.target_column = step.params["mapping"][project.target_column]
                version = create_version(
                    db,
                    project=project,
                    dataset=dataset,
                    df=res.df,
                    parent=input_v,
                    step_id=step.id,
                    carry_columns_from=input_v,
                )
                if res.state:
                    key = f"{project_prefix(project.owner_id, project.id)}states/{step.id}.joblib"
                    get_storage().put_bytes(key, state_to_bytes(res.state))
                    step.fitted_state_key = key
                else:
                    step.fitted_state_key = None
                step.output_version_id = version.id
                step.status = "applied"
                step.applied_at = datetime.now(UTC)
                step.rows_before, step.rows_after = res.rows_before, res.rows_after
                step.cols_before, step.cols_after = res.cols_before, res.cols_after
                warnings = list(res.warnings)
                if res.state:
                    learned = f"Learned on train rows: {jsonable_state(res.state)}"
                    warnings.append({"level": "info", "message": learned[:500]})
                step.warnings = warnings
                dataset.current_version_id = version.id
                prev_output = version.id
            done.append(str(step_id))
        with session_scope() as db:
            pl = db.get(Pipeline, pipeline_id)
            ds_version = db.get(DatasetVersion, prev_output) if prev_output else None
            result = {
                "steps": done,
                "version_id": str(prev_output) if prev_output else None,
                "rows": ds_version.row_count if ds_version else None,
                "pipeline": str(pl.id),
            }
        rep.succeed(result, "Applied")
    except _StepFailed as f:
        _mark_failed(step_ids, f.step_id, f.message)
        rep.fail(f.message)
    except JobCancelled:
        _mark_failed(step_ids, None, "Cancelled")
    except Exception as e:  # noqa: BLE001
        logger.exception("pipeline job failed")
        _mark_failed(step_ids, None, f"{type(e).__name__}: {e}")
        rep.fail(f"Unexpected error: {type(e).__name__}: {e}")


class _StepFailed(Exception):
    def __init__(self, step_id: uuid.UUID, message: str):
        super().__init__(message)
        self.step_id, self.message = step_id, message


def _mark_failed(step_ids: list[uuid.UUID], failed_id: uuid.UUID | None, message: str) -> None:
    """The failed step shows its error and later steps are marked not run. Fixing the failed
    step (PATCH) replays it and everything after it. Already-applied steps keep results."""
    with session_scope() as db:
        hit = False
        for sid in step_ids:
            s = db.get(PipelineStep, sid)
            if s is None or s.status == "applied":
                continue
            if failed_id is None or sid == failed_id:
                s.status = "failed"
                s.error_message = message[:2000]
                hit = True
            elif hit:
                s.status = "failed"
                s.error_message = "Not run because an earlier step failed"
