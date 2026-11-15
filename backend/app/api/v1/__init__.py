from fastapi import APIRouter

from app.api.v1 import admin, auth, chat, datasets, eda, health, jobs, pipeline, projects, validate

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(datasets.router)
api_router.include_router(jobs.router)
api_router.include_router(pipeline.router)
api_router.include_router(eda.router)
api_router.include_router(validate.router)
api_router.include_router(chat.router)
api_router.include_router(admin.router)
