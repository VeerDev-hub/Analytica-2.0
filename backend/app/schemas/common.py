import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORM):
    id: uuid.UUID
    email: str
    display_name: str
    avatar_url: str | None = None
    role: str
    created_at: datetime
    providers: list[str] = []
    has_password: bool = True


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


# ---------------------------------------------------------------- projects
TaskType = Literal["classification", "regression", "forecast", "unsupervised"]


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    target_column: str | None = None
    task_type: TaskType | None = None


class ProjectOut(ORM):
    id: uuid.UUID
    name: str
    description: str | None
    target_column: str | None
    task_type: str | None
    current_pipeline_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ProjectListOut(ProjectOut):
    dataset_name: str | None = None
    rows: int | None = None
    columns: int | None = None
    version_no: int | None = None
    steps: int = 0


class ProjectDetailOut(ProjectOut):
    dataset: "DatasetOut | None" = None


# ---------------------------------------------------------------- datasets
class VersionOut(ORM):
    id: uuid.UUID
    dataset_id: uuid.UUID
    parent_version_id: uuid.UUID | None
    created_by_step_id: uuid.UUID | None
    version_no: int
    row_count: int
    column_count: int
    size_bytes: int
    status: str
    created_at: datetime


class DatasetOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    source_type: str
    original_filename: str | None
    original_format: str | None
    original_size_bytes: int | None
    sheet_name: str | None
    load_options: dict
    current_version_id: uuid.UUID | None
    created_at: datetime
    current_version: VersionOut | None = None


class UploadOut(BaseModel):
    dataset: DatasetOut
    job_id: uuid.UUID


class SetCurrentIn(BaseModel):
    version_id: uuid.UUID


class ColumnOut(ORM):
    id: uuid.UUID
    name: str
    position: int
    dtype: str
    semantic_type: str
    missing_count: int
    unique_count: int
    stats: dict
    description: str | None
    is_private: bool
    is_target: bool


class ColumnPatch(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    is_private: bool | None = None
    is_target: bool | None = None


class RowsOut(BaseModel):
    columns: list[dict]
    rows: list[list]
    row_ids: list[int]
    total: int
    offset: int
    limit: int


class OverviewOut(BaseModel):
    version: VersionOut
    summary: dict
    alerts: list[dict]
    columns: list[ColumnOut]
    load_notes: list[str] = []


# ---------------------------------------------------------------- jobs
class JobOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    step_id: uuid.UUID | None
    job_type: str
    status: str
    progress: int
    message: str | None
    params: dict
    result: dict | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


ProjectDetailOut.model_rebuild()
