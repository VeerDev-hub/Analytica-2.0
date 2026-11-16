from fastapi import APIRouter

from app.api.deps import DB
from app.services import app_settings, plans

router = APIRouter(tags=["plans"])


@router.get("/plans")
def list_plans(db: DB) -> dict:
    """Public plan catalog, used by the pricing section and the Account page."""
    return {
        "plans": plans.catalog(),
        "upgrade_url": app_settings.get(db, "upgrade_url") or None,
    }
