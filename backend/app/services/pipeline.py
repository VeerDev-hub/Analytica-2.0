"""Pipeline use cases (design 4.3): preview on a sample, apply as a job, undo/redo/reset,
edit-and-replay, reorder, delete, split config, recipes.

Invariants
- Steps are ordered by `position`. Status: pending | running | applied | failed | undone.
- The dataset's current version is the output of the last applied step (or the base version).
- Undo moves the pointer to the last applied step's input and marks it `undone`; redo
  reverses that. Adding a new step discards undone steps (their versions stay in the tree).
- Editing, toggling, deleting or reordering re-runs the affected steps in a replay job.
"""

from __future__ import annotations

import uuid

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, ValidationFailed
from app.engine.pipeline import StepSpec, run_step, validate_pipeline
from app.engine.profiling import infer_semantic_type, to_jsonable
from app.engine.transforms import SPLIT_COL, Context, StepError, registry
from app.models import Dataset, DatasetVersion, Pipeline, PipelineStep, Project, User
from app.repositories.access import primary_dataset
from app.services import jobs as job_service
from app.services.quota import ensure_room
from app.services.versions import sample_version_df


class StepInvalid(AppError):
    status_code = 422
    code = "STEP_INVALID"


# ---------------------------------------------------------------- lookups
def steps_of(db: Session, pipeline: Pipeline) -> list[PipelineStep]:
    return list(
        db.scalars(
            select(PipelineStep)
            .where(PipelineStep.pipeline_id == pipeline.id)
            .order_by(PipelineStep.position)
        )
    )


def dataset_of(db: Session, project: Project) -> Dataset:
    ds = primary_dataset(db, project)
    if ds is None or ds.current_version_id is None:
        raise ValidationFailed("Upload a dataset first", code="NO_DATASET")
    return ds


def current_version(db: Session, project: Project) -> DatasetVersion:
    return db.get(DatasetVersion, dataset_of(db, project).current_version_id)


def busy(db: Session, pipeline: Pipeline) -> bool:
    return any(s.status in ("pending", "running") for s in steps_of(db, pipeline))


def ensure_idle(db: Session, pipeline: Pipeline) -> None:
    if busy(db, pipeline):
        raise Conflict("A step is still running. Wait for it to finish.", code="PIPELINE_BUSY")


def context_for(version: DatasetVersion, project: Project) -> Context:
    cols = {
        c["name"]: c["semantic_type"] for c in version.schema_snapshot if c["name"] != SPLIT_COL
    }
    return Context(
        columns=cols,
        target=project.target_column,
        task_type=project.task_type,
        has_split=any(c["name"] == SPLIT_COL for c in version.schema_snapshot),
    )


def spec(step: PipelineStep) -> StepSpec:
    return StepSpec(step.step_type, step.params or {}, step.is_enabled, str(step.id))


def check_step(step_type: str, params: dict, ctx: Context) -> list[dict]:
    if not registry.has(step_type):
        raise StepInvalid(f"Unknown step type '{step_type}'")
    issues = registry.get(step_type).validate(params, ctx)
    errors = [i.to_dict() for i in issues if i.level == "error"]
    if errors:
        raise StepInvalid(errors[0]["message"], details=errors)
    return [i.to_dict() for i in issues if i.level == "warning"]


def check_order(steps: list[StepSpec]) -> None:
    errors = [i.to_dict() for i in validate_pipeline(steps) if i.level == "error"]
    if errors:
        raise StepInvalid(errors[0]["message"], code="LEAKAGE_ORDER", details=errors)


# ---------------------------------------------------------------- preview
def _sample_rows(df: pd.DataFrame, cols: list[str], n: int = 15) -> dict:
    cols = [c for c in cols if c in df.columns][:12]
    part = df[cols].head(n)
    return {
        "columns": cols,
        "rows": [[to_jsonable(v) for v in row] for row in part.itertuples(index=False)],
    }


def preview(db: Session, project: Project, step_type: str, params: dict) -> dict:
    version = current_version(db, project)
    ctx = context_for(version, project)
    warnings = check_step(step_type, params, ctx)
    df = sample_version_df(version, get_settings().preview_sample_rows)
    try:
        res = run_step(
            StepSpec(step_type, params),
            df,
            target=project.target_column,
            task_type=project.task_type,
        )
    except StepError as e:
        raise StepInvalid(str(e)) from e
    except (ValueError, TypeError, KeyError) as e:
        raise StepInvalid(f"The step failed on the sample: {e}") from e
    t = registry.get(step_type)
    touched = [
        c for c in registry.get(step_type).columns(t.defaults(params), ctx) if c in df.columns
    ]
    for key in ("column", "name", "time_column", "stratify_by"):
        if isinstance(params.get(key), str):
            touched.append(params[key])
    show_before = list(dict.fromkeys(touched + res.dropped_columns)) or list(df.columns[:8])
    show_after = list(
        dict.fromkeys([c for c in touched if c in res.df.columns] + res.added_columns)
    ) or list(res.df.columns[:8])
    col_changes = []
    for c in show_after:
        if c in df.columns and c in res.df.columns:
            col_changes.append(
                {
                    "column": c,
                    "missing_before": int(df[c].isna().sum()),
                    "missing_after": int(res.df[c].isna().sum()),
                    "type_before": infer_semantic_type(df[c], c),
                    "type_after": infer_semantic_type(res.df[c], c),
                }
            )
    return {
        "step_type": step_type,
        "describe": t.describe(params),
        "explain": t.explain_text,
        "sample_rows": len(df),
        "summary": res.summary(),
        "warnings": warnings + res.warnings,
        "before": _sample_rows(df, show_before),
        "after": _sample_rows(res.df, show_after),
        "column_changes": col_changes,
        "split_counts": (
            res.df[SPLIT_COL].value_counts().to_dict() if SPLIT_COL in res.df.columns else None
        ),
    }


# ---------------------------------------------------------------- apply / replay
def _launch(
    db: Session,
    user: User,
    project: Project,
    pipeline: Pipeline,
    steps: list[PipelineStep],
    job_type: str,
) -> uuid.UUID:
    for s in steps:
        s.status = "pending"
        s.error_message = None
    job = job_service.create_job(
        db,
        project_id=project.id,
        user_id=user.id,
        job_type=job_type,
        step_id=steps[0].id if steps else None,
        params={"pipeline_id": str(pipeline.id), "step_ids": [str(s.id) for s in steps]},
    )
    from app.tasks.pipeline import task_run_steps

    job_service.enqueue(db, job, task_run_steps)
    return job.id


def _discard_undone(db: Session, pipeline: Pipeline, include_failed: bool = False) -> None:
    drop = ("undone", "failed") if include_failed else ("undone",)
    for s in steps_of(db, pipeline):
        if s.status in drop:
            db.delete(s)
    db.flush()


def add_step(
    db: Session, user: User, project: Project, pipeline: Pipeline, step_type: str, params: dict
) -> tuple[PipelineStep, uuid.UUID]:
    ensure_idle(db, pipeline)
    ensure_room(db, user)
    version = current_version(db, project)
    warnings = check_step(step_type, params, context_for(version, project))
    _discard_undone(db, pipeline, include_failed=True)
    existing = [s for s in steps_of(db, pipeline) if s.status == "applied"]
    check_order([spec(s) for s in existing] + [StepSpec(step_type, params)])
    t = registry.get(step_type)
    step = PipelineStep(
        pipeline_id=pipeline.id,
        position=(existing[-1].position + 1) if existing else 1,
        step_type=step_type,
        phase=t.phase,
        params=params,
        column_scope={},
        status="pending",
        input_version_id=version.id,
        warnings=warnings,
    )
    db.add(step)
    db.flush()
    if step_type == "split":
        pipeline.split_config = params
    return step, _launch(db, user, project, pipeline, [step], "run_step")


def replay_from(
    db: Session,
    user: User,
    project: Project,
    pipeline: Pipeline,
    first: PipelineStep,
    input_version_id: uuid.UUID,
) -> uuid.UUID | None:
    """Re-run `first` and every later applied step, starting from `input_version_id`."""
    _discard_undone(db, pipeline)
    todo = [
        s
        for s in steps_of(db, pipeline)
        if s.position >= first.position and s.status in ("applied", "pending", "failed")
    ]
    if not todo:
        ds = dataset_of(db, project)
        ds.current_version_id = input_version_id
        db.commit()
        return None
    todo[0].input_version_id = input_version_id
    return _launch(db, user, project, pipeline, todo, "replay")


def patch_step(
    db: Session,
    user: User,
    project: Project,
    pipeline: Pipeline,
    step: PipelineStep,
    params: dict | None,
    is_enabled: bool | None,
) -> uuid.UUID | None:
    ensure_idle(db, pipeline)
    ensure_room(db, user)
    if step.status not in ("applied", "failed"):
        raise Conflict("Only applied steps can be edited; redo it first", code="STEP_NOT_APPLIED")
    if params is not None:
        input_v = db.get(DatasetVersion, step.input_version_id)
        step.warnings = check_step(step.step_type, params, context_for(input_v, project))
        step.params = params
        if step.step_type == "split":
            pipeline.split_config = params
    if is_enabled is not None:
        step.is_enabled = is_enabled
    if step.status == "failed":
        step.status = "applied"
    check_order([spec(s) for s in steps_of(db, pipeline) if s.status in ("applied", "failed")])
    return replay_from(db, user, project, pipeline, step, step.input_version_id)


def delete_step(
    db: Session, user: User, project: Project, pipeline: Pipeline, step: PipelineStep
) -> uuid.UUID | None:
    ensure_idle(db, pipeline)
    input_v = step.input_version_id
    later = [
        s for s in steps_of(db, pipeline) if s.position > step.position and s.status == "applied"
    ]
    remaining = [
        spec(s) for s in steps_of(db, pipeline) if s.status == "applied" and s.id != step.id
    ]
    check_order(remaining)
    if step.step_type == "split":
        pipeline.split_config = None
    was_applied = step.status == "applied"
    db.delete(step)
    db.flush()
    if not was_applied:
        db.commit()
        return None
    if later:
        return replay_from(db, user, project, pipeline, later[0], input_v)
    ds = dataset_of(db, project)
    ds.current_version_id = input_v
    db.commit()
    return None


def reorder(
    db: Session, user: User, project: Project, pipeline: Pipeline, step_ids: list[uuid.UUID]
) -> uuid.UUID | None:
    ensure_idle(db, pipeline)
    ensure_room(db, user)
    applied = [s for s in steps_of(db, pipeline) if s.status == "applied"]
    if sorted(map(str, step_ids)) != sorted(str(s.id) for s in applied):
        raise ValidationFailed("Send every applied step id exactly once")
    by_id = {str(s.id): s for s in applied}
    new_order = [by_id[str(i)] for i in step_ids]
    check_order([spec(s) for s in new_order])
    first_changed = next(
        (i for i, (a, b) in enumerate(zip(applied, new_order, strict=True)) if a.id != b.id), None
    )
    if first_changed is None:
        return None
    base_input = applied[first_changed].input_version_id
    positions = sorted(s.position for s in applied)
    for pos, s in zip(positions, new_order, strict=True):
        s.position = pos + 100_000  # avoid transient clashes, then normalise
    db.flush()
    for pos, s in zip(positions, new_order, strict=True):
        s.position = pos
    db.flush()
    return replay_from(db, user, project, pipeline, new_order[first_changed], base_input)


def undo(db: Session, project: Project, pipeline: Pipeline) -> PipelineStep:
    ensure_idle(db, pipeline)
    applied = [s for s in steps_of(db, pipeline) if s.status == "applied"]
    if not applied:
        raise Conflict("Nothing to undo", code="NOTHING_TO_UNDO")
    last = applied[-1]
    last.status = "undone"
    dataset_of(db, project).current_version_id = last.input_version_id
    if last.step_type == "split":
        pipeline.split_config = None
    db.commit()
    return last


def redo(db: Session, project: Project, pipeline: Pipeline) -> PipelineStep:
    ensure_idle(db, pipeline)
    ds = dataset_of(db, project)
    undone = [s for s in steps_of(db, pipeline) if s.status == "undone"]
    nxt = next(
        (s for s in undone if s.input_version_id == ds.current_version_id and s.output_version_id),
        None,
    )
    if nxt is None:
        raise Conflict("Nothing to redo", code="NOTHING_TO_REDO")
    nxt.status = "applied"
    ds.current_version_id = nxt.output_version_id
    if nxt.step_type == "split":
        pipeline.split_config = nxt.params
    db.commit()
    return nxt


def reset(db: Session, project: Project, pipeline: Pipeline) -> None:
    ensure_idle(db, pipeline)
    for s in steps_of(db, pipeline):
        if s.status == "applied":
            s.status = "undone"
    dataset_of(db, project).current_version_id = pipeline.base_version_id
    pipeline.split_config = None
    db.commit()


def set_split(
    db: Session, user: User, project: Project, pipeline: Pipeline, config: dict
) -> tuple[PipelineStep, uuid.UUID | None]:
    existing = next(
        (s for s in steps_of(db, pipeline) if s.step_type == "split" and s.status == "applied"),
        None,
    )
    if existing:
        return existing, patch_step(db, user, project, pipeline, existing, config, None)
    ensure_idle(db, pipeline)
    ensure_room(db, user)
    _discard_undone(db, pipeline, include_failed=True)
    applied = [s for s in steps_of(db, pipeline) if s.status == "applied"]
    first_fitted = next(
        (
            s
            for s in applied
            if registry.has(s.step_type) and registry.get(s.step_type).phase == "post_split"
        ),
        None,
    )
    if first_fitted is None:
        return add_step(db, user, project, pipeline, "split", config)
    # Insert the split right before the first step that learns from data, then replay, so
    # those steps are re-fitted on training rows only.
    input_v = db.get(DatasetVersion, first_fitted.input_version_id)
    warnings = check_step("split", config, context_for(input_v, project))
    for s in applied:
        if s.position >= first_fitted.position:
            s.position += 1
    step = PipelineStep(
        pipeline_id=pipeline.id,
        position=first_fitted.position - 1,
        step_type="split",
        phase="split",
        params=config,
        column_scope={},
        status="pending",
        input_version_id=input_v.id,
        warnings=warnings,
    )
    db.add(step)
    db.flush()
    pipeline.split_config = config
    return step, replay_from(db, user, project, pipeline, step, input_v.id)


def append_steps(
    db: Session, user: User, project: Project, pipeline: Pipeline, specs: list[StepSpec]
) -> uuid.UUID:
    """Apply several steps in one job (recipes, chat proposals)."""
    ensure_idle(db, pipeline)
    ensure_room(db, user)
    if not specs:
        raise ValidationFailed("No steps to apply")
    for s in specs:
        if not registry.has(s.step_type):
            raise StepInvalid(f"Unknown step type '{s.step_type}'")
    _discard_undone(db, pipeline, include_failed=True)
    existing = [s for s in steps_of(db, pipeline) if s.status == "applied"]
    check_order([spec(s) for s in existing] + specs)
    version = current_version(db, project)
    pos = (existing[-1].position + 1) if existing else 1
    new_steps = []
    for i, s in enumerate(specs):
        st = PipelineStep(
            pipeline_id=pipeline.id,
            position=pos + i,
            step_type=s.step_type,
            phase=registry.get(s.step_type).phase,
            params=s.params,
            column_scope={},
            is_enabled=s.is_enabled,
            status="pending",
            input_version_id=version.id if i == 0 else None,
            warnings=[],
        )
        db.add(st)
        new_steps.append(st)
    db.flush()
    return _launch(db, user, project, pipeline, new_steps, "replay")
