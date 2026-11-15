import uuid

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.engine.pipeline import validate_pipeline
from app.engine.transforms import registry
from app.models import Pipeline, PipelineStep, Recipe, RecipeStep
from app.repositories.access import get_pipeline, get_project, get_step
from app.schemas.pipeline import (
    ApplyRecipeIn,
    JobRef,
    PipelineOut,
    RecipeIn,
    RecipeOut,
    ReorderIn,
    StepIn,
    StepOut,
    StepPatch,
)
from app.services import pipeline as svc
from app.services.pipeline import StepSpec

router = APIRouter(tags=["pipeline"])


def step_out(s: PipelineStep) -> StepOut:
    out = StepOut.model_validate(s)
    if registry.has(s.step_type):
        t = registry.get(s.step_type)
        out.label = t.label
        try:
            out.describe = t.describe(s.params or {})
        except Exception:  # noqa: BLE001 - description is cosmetic
            out.describe = t.label
    return out


def pipeline_out(db, project, pipeline: Pipeline) -> PipelineOut:
    steps = svc.steps_of(db, pipeline)
    ds = svc.primary_dataset(db, project)
    current = ds.current_version_id if ds else None
    applied = [s for s in steps if s.status == "applied"]
    can_redo = any(
        s.status == "undone" and s.input_version_id == current and s.output_version_id
        for s in steps
    )
    issues = [i.to_dict() for i in validate_pipeline([svc.spec(s) for s in applied])]
    if project.target_column is None and any(
        registry.has(s.step_type) and registry.get(s.step_type).phase == "post_split"
        for s in applied
    ):
        issues.append({"level": "warning", "message": "No target column set", "field": None})
    if (
        applied
        and not any(s.step_type == "split" for s in applied)
        and any(
            registry.get(s.step_type).phase == "post_split"
            for s in applied
            if registry.has(s.step_type)
        )
    ):
        issues.append(
            {
                "level": "warning",
                "field": None,
                "message": "Steps that learn from data ran without a split: add a "
                "split before them to avoid leakage",
            }
        )
    return PipelineOut(
        id=pipeline.id,
        name=pipeline.name,
        base_version_id=pipeline.base_version_id,
        current_version_id=current,
        split_config=pipeline.split_config,
        steps=[step_out(s) for s in steps],
        can_undo=bool(applied),
        can_redo=can_redo,
        busy=any(s.status in ("pending", "running") for s in steps),
        issues=issues,
    )


def _active(db, user, project_id: uuid.UUID):
    project = get_project(db, user, project_id)
    if project.current_pipeline_id is None:
        raise NotFound("Upload a dataset to start a pipeline", code="NO_PIPELINE")
    return project, db.get(Pipeline, project.current_pipeline_id)


@router.get("/steps/catalog")
def catalog() -> list[dict]:
    return registry.catalog()


@router.get("/projects/{project_id}/pipeline", response_model=PipelineOut)
def get_active(project_id: uuid.UUID, user: CurrentUser, db: DB) -> PipelineOut:
    project, pl = _active(db, user, project_id)
    return pipeline_out(db, project, pl)


@router.post("/pipeline/{pipeline_id}/steps/preview")
def preview(pipeline_id: uuid.UUID, body: StepIn, user: CurrentUser, db: DB) -> dict:
    pl, project = get_pipeline(db, user, pipeline_id)
    return svc.preview(db, project, body.step_type, body.params)


@router.post("/pipeline/{pipeline_id}/steps", response_model=JobRef, status_code=202)
def add(pipeline_id: uuid.UUID, body: StepIn, user: CurrentUser, db: DB) -> JobRef:
    pl, project = get_pipeline(db, user, pipeline_id)
    step, job_id = svc.add_step(db, user, project, pl, body.step_type, body.params)
    return JobRef(job_id=job_id, step_id=step.id)


@router.patch("/steps/{step_id}", response_model=JobRef)
def patch(step_id: uuid.UUID, body: StepPatch, user: CurrentUser, db: DB) -> JobRef:
    step, pl, project = get_step(db, user, step_id)
    job_id = svc.patch_step(db, user, project, pl, step, body.params, body.is_enabled)
    return JobRef(job_id=job_id, step_id=step.id)


@router.delete("/steps/{step_id}", response_model=JobRef)
def delete(step_id: uuid.UUID, user: CurrentUser, db: DB) -> JobRef:
    step, pl, project = get_step(db, user, step_id)
    return JobRef(job_id=svc.delete_step(db, user, project, pl, step))


@router.post("/pipeline/{pipeline_id}/reorder", response_model=JobRef)
def reorder(pipeline_id: uuid.UUID, body: ReorderIn, user: CurrentUser, db: DB) -> JobRef:
    pl, project = get_pipeline(db, user, pipeline_id)
    return JobRef(job_id=svc.reorder(db, user, project, pl, body.step_ids))


@router.post("/pipeline/{pipeline_id}/undo", response_model=PipelineOut)
def undo(pipeline_id: uuid.UUID, user: CurrentUser, db: DB) -> PipelineOut:
    pl, project = get_pipeline(db, user, pipeline_id)
    svc.undo(db, project, pl)
    return pipeline_out(db, project, pl)


@router.post("/pipeline/{pipeline_id}/redo", response_model=PipelineOut)
def redo(pipeline_id: uuid.UUID, user: CurrentUser, db: DB) -> PipelineOut:
    pl, project = get_pipeline(db, user, pipeline_id)
    svc.redo(db, project, pl)
    return pipeline_out(db, project, pl)


@router.post("/pipeline/{pipeline_id}/reset", response_model=PipelineOut)
def reset(pipeline_id: uuid.UUID, user: CurrentUser, db: DB) -> PipelineOut:
    pl, project = get_pipeline(db, user, pipeline_id)
    svc.reset(db, project, pl)
    return pipeline_out(db, project, pl)


@router.put("/pipeline/{pipeline_id}/split", response_model=JobRef)
def set_split(pipeline_id: uuid.UUID, body: dict, user: CurrentUser, db: DB) -> JobRef:
    pl, project = get_pipeline(db, user, pipeline_id)
    step, job_id = svc.set_split(db, user, project, pl, body)
    return JobRef(job_id=job_id, step_id=step.id)


# ---------------------------------------------------------------- recipes
def recipe_out(db, r: Recipe) -> RecipeOut:
    out = RecipeOut.model_validate(r)
    out.steps = [
        {"step_type": s.step_type, "params": s.params, "phase": s.phase}
        for s in db.scalars(
            select(RecipeStep).where(RecipeStep.recipe_id == r.id).order_by(RecipeStep.position)
        )
    ]
    return out


@router.get("/recipes", response_model=list[RecipeOut])
def list_recipes(user: CurrentUser, db: DB) -> list[RecipeOut]:
    rs = db.scalars(
        select(Recipe)
        .where((Recipe.owner_id == user.id) | Recipe.is_public)
        .order_by(Recipe.created_at.desc())
    )
    return [recipe_out(db, r) for r in rs]


@router.post("/recipes", response_model=RecipeOut, status_code=201)
def save_recipe(body: RecipeIn, user: CurrentUser, db: DB) -> RecipeOut:
    project, pl = _active(db, user, body.project_id)
    steps = [
        s
        for s in svc.steps_of(db, pl)
        if s.status == "applied" and s.is_enabled and (body.include_split or s.step_type != "split")
    ]
    if not steps:
        raise svc.ValidationFailed("The pipeline has no applied steps to save")
    r = Recipe(owner_id=user.id, name=body.name, description=body.description)
    db.add(r)
    db.flush()
    for i, s in enumerate(steps, start=1):
        db.add(
            RecipeStep(
                recipe_id=r.id,
                position=i,
                step_type=s.step_type,
                phase=s.phase,
                params=s.params,
                column_scope=s.column_scope or {},
            )
        )
    db.commit()
    return recipe_out(db, r)


@router.delete("/recipes/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: uuid.UUID, user: CurrentUser, db: DB) -> Response:
    r = db.get(Recipe, recipe_id)
    if r is None or r.owner_id != user.id:
        raise NotFound("Recipe not found")
    db.delete(r)
    db.commit()
    return Response(status_code=204)


@router.post("/projects/{project_id}/apply-recipe", response_model=JobRef, status_code=202)
def apply_recipe(project_id: uuid.UUID, body: ApplyRecipeIn, user: CurrentUser, db: DB) -> JobRef:
    project, pl = _active(db, user, project_id)
    r = db.get(Recipe, body.recipe_id)
    if r is None or (r.owner_id != user.id and not r.is_public):
        raise NotFound("Recipe not found")
    specs = [
        StepSpec(s.step_type, s.params)
        for s in db.scalars(
            select(RecipeStep).where(RecipeStep.recipe_id == r.id).order_by(RecipeStep.position)
        )
    ]
    if any(s.step_type == "split" for s in specs) and any(
        s.step_type == "split" and s.status == "applied" for s in svc.steps_of(db, pl)
    ):
        specs = [s for s in specs if s.step_type != "split"]
    return JobRef(job_id=svc.append_steps(db, user, project, pl, specs))
