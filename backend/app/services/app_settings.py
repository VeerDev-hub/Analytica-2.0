"""Admin-editable runtime settings (stored in `app_settings`, defaults from env/config).

Reads are cached for a few seconds per process so hot paths don't hit the database on
every request; a change shows up everywhere within that window.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.models import AppSetting

CHAT_MODELS = ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


def _defaults() -> dict[str, Any]:
    s = get_settings()
    return {
        "chat_enabled": True,
        "chat_model": s.chat_model,
        "chat_effort": s.chat_effort,
        "signups_open": True,
        "max_upload_mb": s.max_upload_mb,
        "announcement": {"text": "", "tone": "info"},
        "storage_quota_mb": 5120,
    }


SCHEMA: dict[str, dict] = {
    "chat_enabled": {
        "type": "bool",
        "label": "Chat assistant",
        "help": "Turn the data assistant on or off for everyone. It also needs "
        "GEMINI_API_KEY on the server.",
    },
    "chat_model": {
        "type": "select",
        "options": CHAT_MODELS,
        "label": "Chat model",
        "help": "Flash is the free-tier default. Flash-Lite is faster; Pro is stronger "
        "but has tighter free-tier limits.",
    },
    "chat_effort": {
        "type": "select",
        "options": EFFORTS,
        "label": "Chat effort",
        "help": "Sets the Gemini thinking budget. Higher thinks longer and uses more tokens.",
    },
    "signups_open": {
        "type": "bool",
        "label": "New sign-ups",
        "help": "When off, only existing accounts can sign in (email or OAuth).",
    },
    "max_upload_mb": {
        "type": "int",
        "min": 1,
        "max": 2000,
        "label": "Upload limit (MB)",
        "help": "Largest file a user can upload.",
    },
    "storage_quota_mb": {
        "type": "int",
        "min": 100,
        "max": 1_000_000,
        "label": "Storage per account (MB)",
        "help": "Default limit for every account (5120 MB = 5 GB). Uploads, cleaning versions "
        "and exports all count. You can give individual users more in the Users tab.",
    },
    "announcement": {
        "type": "announcement",
        "label": "Announcement banner",
        "help": "Shown at the top of every page. Leave empty to hide.",
    },
}

_cache: dict[str, Any] = {"at": 0.0, "values": None}
TTL_S = 5.0


def all_settings(db: Session, fresh: bool = False) -> dict[str, Any]:
    if not fresh and _cache["values"] is not None and time.monotonic() - _cache["at"] < TTL_S:
        return dict(_cache["values"])
    values = _defaults()
    for row in db.scalars(select(AppSetting)):
        if row.key in values:
            values[row.key] = row.value
    if values["chat_model"] not in CHAT_MODELS:  # e.g. a model saved before a provider switch
        values["chat_model"] = get_settings().chat_model
    _cache.update(at=time.monotonic(), values=values)
    return dict(values)


def get(db: Session, key: str) -> Any:
    return all_settings(db)[key]


def _validate(key: str, value: Any) -> Any:
    spec = SCHEMA.get(key)
    if spec is None:
        raise ValidationFailed(f"Unknown setting '{key}'")
    t = spec["type"]
    if t == "bool" and isinstance(value, bool):
        return value
    if t == "int" and isinstance(value, int) and not isinstance(value, bool):
        if spec["min"] <= value <= spec["max"]:
            return value
        raise ValidationFailed(f"{spec['label']} must be between {spec['min']} and {spec['max']}")
    if t == "select" and value in spec["options"]:
        return value
    if t == "announcement" and isinstance(value, dict):
        text = str(value.get("text", ""))[:300]
        tone = value.get("tone", "info")
        if tone not in ("info", "warn", "ok"):
            tone = "info"
        return {"text": text, "tone": tone}
    raise ValidationFailed(f"Invalid value for {spec['label']}")


def update(db: Session, changes: dict[str, Any], user_id: uuid.UUID) -> dict[str, Any]:
    clean = {k: _validate(k, v) for k, v in changes.items()}
    for k, v in clean.items():
        row = db.get(AppSetting, k)
        if row is None:
            db.add(AppSetting(key=k, value=v, updated_by=user_id))
        else:
            row.value = v
            row.updated_by = user_id
    db.commit()
    _cache["values"] = None
    return all_settings(db, fresh=True)
