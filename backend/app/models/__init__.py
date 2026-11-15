"""Import every model so Base.metadata is complete (Alembic autogenerate, tests)."""

from app.models.chat import ChatMessage, ChatSession, EmbeddingChunk
from app.models.job import Export, Job, Report
from app.models.pipeline import DatasetSplit, Pipeline, PipelineStep, Recipe, RecipeStep
from app.models.project import ColumnProfile, Dataset, DatasetVersion, Project
from app.models.user import AppSetting, OAuthAccount, User

__all__ = [
    "AppSetting",
    "OAuthAccount",
    "ChatMessage",
    "ChatSession",
    "ColumnProfile",
    "Dataset",
    "DatasetSplit",
    "DatasetVersion",
    "EmbeddingChunk",
    "Export",
    "Job",
    "Pipeline",
    "PipelineStep",
    "Project",
    "Recipe",
    "RecipeStep",
    "Report",
    "User",
]
