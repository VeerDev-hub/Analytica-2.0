"""FastAPI application factory."""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging, request_id_var
from app.core.ratelimit import check as rate_limit

logger = logging.getLogger("app.request")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            # Coarse per-IP ceiling for the whole API; routes add tighter limits.
            if request.url.path.startswith("/api/") and not request.url.path.endswith("/livez"):
                try:
                    rate_limit(request, "api:ip", limit=300, window_s=60)
                except Exception as exc:  # noqa: BLE001 - AppError → same JSON shape as routes
                    from app.core.errors import AppError, TooManyRequests

                    if not isinstance(exc, AppError):
                        raise
                    from fastapi.responses import JSONResponse

                    headers = (
                        {"Retry-After": str(exc.retry_after)}
                        if isinstance(exc, TooManyRequests)
                        else None
                    )
                    body = {"code": exc.code, "message": exc.message, "details": exc.details}
                    return JSONResponse(
                        {"error": body},
                        status_code=exc.status_code,
                        headers=headers,
                    )
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "%s %s -> %s in %.1f ms",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - start) * 1000,
            )
            return response
        finally:
            request_id_var.reset(token)

    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
