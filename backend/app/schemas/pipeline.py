import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORM


class StepOut(ORM):
    id: uuid.UUID
    position: int
    step_type: str
    phase: str
    params: dict
    is_enabled: bool
    status: str
    input_version_id: uuid.UUID | None
    output_version_id: uuid.UUID | None
    rows_before: int | None
    rows_after: int | None
    cols_before: int | None
    cols_after: int | None
    warnings: list
    error_message: str | None
    applied_at: datetime | None
    label: str = ""
    describe: str = ""


class PipelineOut(BaseModel):
    id: uuid.UUID
    name: str
    base_version_id: uuid.UUID
    current_version_id: uuid.UUID | None
    split_config: dict | None
    steps: list[StepOut]
    can_undo: bool
    can_redo: bool
    busy: bool
    issues: list[dict]


class StepIn(BaseModel):
    step_type: str = Field(min_length=1, max_length=64)
    params: dict = Field(default_factory=dict)


class StepPatch(BaseModel):
    params: dict | None = None
    is_enabled: bool | None = None


class ReorderIn(BaseModel):
    step_ids: list[uuid.UUID]


class JobRef(BaseModel):
    job_id: uuid.UUID | None
    step_id: uuid.UUID | None = None


class ChartSpec(BaseModel):
    kind: str
    x: str | None = None
    y: str | None = None
    color: str | None = None
    agg: str = "count"
    bins: int | None = Field(default=None, ge=2, le=200)
    top: int | None = Field(default=None, ge=1, le=200)
    log_y: bool = False
    title: str | None = Field(default=None, max_length=200)
    method: str | None = None


class RecipeIn(BaseModel):
    project_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    include_split: bool = True


class RecipeOut(ORM):
    id: uuid.UUID
    name: str
    description: str | None
    is_public: bool
    created_at: datetime
    steps: list[dict] = []


class ApplyRecipeIn(BaseModel):
    recipe_id: uuid.UUID
