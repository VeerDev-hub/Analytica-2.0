from fastapi import APIRouter, Response, status
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.core.config import get_settings
from app.schemas.health import HealthResponse
from app.services.health import run_checks

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(response: Response) -> HealthResponse:
    """Liveness + dependency check. Returns 503 if any dependency is down."""
    deps = await run_in_threadpool(run_checks)
    healthy = all(d["status"] == "ok" for d in deps.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if healthy else "degraded",
        version=__version__,
        environment=get_settings().environment,
        dependencies=deps,
    )


@router.get("/livez", include_in_schema=False)
async def livez() -> dict[str, str]:
    """Cheap liveness probe for the load balancer (no dependency calls)."""
    return {"status": "ok"}


@router.get("/meta")
def meta() -> dict:
    """Public, unauthenticated app info for the UI shell (banner, sign-in options)."""
    from app.chat.orchestrator import chat_enabled
    from app.core.db import _session_factory
    from app.services import app_settings, oauth

    with _session_factory()() as db:
        cfg = app_settings.all_settings(db)
    return {
        "version": __version__,
        "announcement": cfg["announcement"],
        "signups_open": cfg["signups_open"],
        "providers": oauth.enabled_providers(),
        "chat_enabled": chat_enabled() and bool(cfg["chat_enabled"]),
        "max_upload_mb": cfg["max_upload_mb"],
    }
