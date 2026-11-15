import json
import uuid
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.chat.orchestrator import chat_enabled, get_client, run_chat
from app.core.errors import Conflict, NotFound
from app.models import ChatMessage, ChatSession, Pipeline
from app.repositories.access import get_chat_session, get_project
from app.schemas.common import ORM
from app.services import pipeline as pipeline_service

router = APIRouter(tags=["chat"])


class SessionOut(ORM):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(ORM):
    id: uuid.UUID
    role: str
    content: str
    tool_calls: list | None
    citations: list | None
    proposed_step: dict | None
    created_at: datetime


class AskIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


def _chat_on(db) -> bool:
    from app.services import app_settings

    return chat_enabled() and bool(app_settings.get(db, "chat_enabled"))


@router.get("/chat/status")
def status(user: CurrentUser, db: DB) -> dict:
    return {"enabled": _chat_on(db)}


@router.get("/projects/{project_id}/chat/sessions", response_model=list[SessionOut])
def list_sessions(project_id: uuid.UUID, user: CurrentUser, db: DB) -> list[ChatSession]:
    project = get_project(db, user, project_id)
    return list(
        db.scalars(
            select(ChatSession)
            .where(ChatSession.project_id == project.id, ChatSession.user_id == user.id)
            .order_by(ChatSession.updated_at.desc())
            .limit(50)
        )
    )


@router.post("/projects/{project_id}/chat/sessions", response_model=SessionOut, status_code=201)
def create_session(project_id: uuid.UUID, user: CurrentUser, db: DB) -> ChatSession:
    project = get_project(db, user, project_id)
    s = ChatSession(project_id=project.id, user_id=user.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/chat/sessions/{session_id}/messages", response_model=list[MessageOut])
def messages(session_id: uuid.UUID, user: CurrentUser, db: DB) -> list[ChatMessage]:
    s, _ = get_chat_session(db, user, session_id)
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == s.id)
            .order_by(ChatMessage.created_at)
        )
    )


@router.post("/chat/sessions/{session_id}/messages")
def ask(session_id: uuid.UUID, body: AskIn, user: CurrentUser, db: DB) -> StreamingResponse:
    """SSE stream: text deltas, tool calls with their query/rows, then `done`."""
    s, project = get_chat_session(db, user, session_id)
    get_client()  # raises 503 CHAT_DISABLED before the stream starts
    if not _chat_on(db):
        from app.core.errors import ServiceUnavailable

        raise ServiceUnavailable("The administrator has turned chat off.", code="CHAT_DISABLED")
    version = pipeline_service.current_version(db, project)

    ids = (s.id, project.id, version.id)

    def events():
        # Own session: the request-scoped one may be closed before the stream finishes.
        from app.core.db import _session_factory
        from app.models import DatasetVersion, Project

        with _session_factory()() as sdb:
            sess = sdb.get(ChatSession, ids[0])
            proj = sdb.get(Project, ids[1])
            ver = sdb.get(DatasetVersion, ids[2])
            for ev in run_chat(sdb, sess, proj, ver, body.content.strip()):
                yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/messages/{message_id}/approve")
def approve(message_id: uuid.UUID, user: CurrentUser, db: DB) -> dict:
    """Apply the step the assistant proposed (design 4.5: step proposals need approval)."""
    m = db.get(ChatMessage, message_id)
    if m is None or not m.proposed_step:
        raise NotFound("No proposed step on this message")
    s, project = get_chat_session(db, user, m.session_id)
    step = dict(m.proposed_step)
    if step.get("status") != "proposed":
        raise Conflict("This proposal was already handled", code="ALREADY_APPLIED")
    pl = db.get(Pipeline, project.current_pipeline_id)
    new_step, job_id = pipeline_service.add_step(
        db, user, project, pl, step["step_type"], step.get("params") or {}
    )
    step["status"] = "applied"
    step["step_id"] = str(new_step.id)
    m.proposed_step = step
    db.commit()
    return {"job_id": str(job_id), "step_id": str(new_step.id)}
