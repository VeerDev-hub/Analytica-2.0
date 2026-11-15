from typing import Literal

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    status: Literal["ok", "down"]
    latency_ms: float
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    dependencies: dict[str, DependencyStatus]
