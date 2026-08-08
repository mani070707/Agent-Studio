import jsonschema
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.conversations.service import (MAX_MESSAGE_CHARACTERS, ConversationMemoryError,
                                       ConversationMemoryService, expires_at)
from app.core.auth import get_current_user_id
from app.core.secret_resolver import SecretResolutionError
from app.db.crud_helpers import get_owned_or_404
from app.db.models import (Agent, AgentVersion, ConversationMessage, ConversationThread, Run,
                           RunStep)
from app.db.session import get_db
from app.runs.executor import execute_run

router = APIRouter(tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str = "New conversation"


class ConversationUpdate(BaseModel):
    title: str | None = None
    status: Literal["active", "archived"] | None = None


class ConversationMessageIn(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARACTERS)
    variables: dict = {}


def thread_out(row: ConversationThread, count: int = 0) -> dict:
    return {"id": row.id, "agent_id": row.agent_id, "agent_version_id": row.agent_version_id,
            "title": row.title, "status": row.status, "memory_enabled": row.memory_enabled,
            "summary_present": bool(row.summary), "summary_token_count": row.summary_token_count,
            "message_token_count": row.message_token_count, "message_count": count,
            "expires_at": row.expires_at, "created_at": row.created_at, "updated_at": row.updated_at}


def message_out(row: ConversationMessage) -> dict:
    return {"id": row.id, "thread_id": row.thread_id, "role": row.role, "content": row.content,
            "run_id": row.run_id, "token_count": row.token_count, "created_at": row.created_at}


@router.get("/conversations")
def list_conversations(agent_id: str | None = None, db: Session = Depends(get_db),
                       user_id: str = Depends(get_current_user_id)):
    query = db.query(ConversationThread).filter(ConversationThread.user_id == user_id)
    if agent_id: query = query.filter(ConversationThread.agent_id == agent_id)
    rows = query.order_by(ConversationThread.updated_at.desc()).all()
    return [thread_out(row, db.query(ConversationMessage).filter(
        ConversationMessage.thread_id == row.id, ConversationMessage.user_id == user_id).count()) for row in rows]


@router.post("/agents/{agent_id}/versions/{version_id}/conversations", status_code=201)
def create_conversation(agent_id: str, version_id: str, body: ConversationCreate,
                        response: Response, db: Session = Depends(get_db),
                        user_id: str = Depends(get_current_user_id)):
    agent = get_owned_or_404(db, Agent, agent_id, user_id)
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id,
        AgentVersion.agent_id == agent_id, AgentVersion.user_id == user_id).first()
    if not version: raise HTTPException(status_code=404, detail="Agent version not found")
    if agent.agent_type != "chat": raise HTTPException(status_code=409, detail="Only chat agents support conversations")
    if not version.harness_config.get("memory", {}).get("vector_memory_enabled", False):
        raise HTTPException(status_code=409, detail="Conversation memory is not enabled for this version")
    title = body.title.strip() or "New conversation"
    row = ConversationThread(user_id=user_id, agent_id=agent_id, agent_version_id=version_id,
                             title=title[:120], expires_at=expires_at())
    db.add(row); db.commit(); db.refresh(row)
    response.headers["Location"] = f"/conversations/{row.id}"
    return thread_out(row)


@router.get("/conversations/{thread_id}")
def get_conversation(thread_id: str, db: Session = Depends(get_db),
                     user_id: str = Depends(get_current_user_id)):
    row = get_owned_or_404(db, ConversationThread, thread_id, user_id)
    count = db.query(ConversationMessage).filter(ConversationMessage.thread_id == thread_id,
                                                 ConversationMessage.user_id == user_id).count()
    return thread_out(row, count)


@router.put("/conversations/{thread_id}")
def update_conversation(thread_id: str, body: ConversationUpdate, db: Session = Depends(get_db),
                        user_id: str = Depends(get_current_user_id)):
    row = get_owned_or_404(db, ConversationThread, thread_id, user_id)
    if body.title is not None:
        title = body.title.strip()
        if not title: raise HTTPException(status_code=422, detail="Conversation title cannot be blank")
        row.title = title[:120]
    if body.status is not None: row.status = body.status
    row.updated_at = datetime.now(timezone.utc); db.commit(); db.refresh(row)
    return thread_out(row)


@router.delete("/conversations/{thread_id}", status_code=204)
def delete_conversation(thread_id: str, db: Session = Depends(get_db),
                        user_id: str = Depends(get_current_user_id)):
    row = get_owned_or_404(db, ConversationThread, thread_id, user_id)
    db.delete(row); db.commit()


@router.get("/conversations/{thread_id}/messages")
def list_messages(thread_id: str, db: Session = Depends(get_db),
                  user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, ConversationThread, thread_id, user_id)
    rows = db.query(ConversationMessage).filter(ConversationMessage.thread_id == thread_id,
        ConversationMessage.user_id == user_id).order_by(ConversationMessage.created_at,
                                                           ConversationMessage.id).all()
    return [message_out(row) for row in rows]


@router.post("/conversations/{thread_id}/messages")
async def send_message(thread_id: str, body: ConversationMessageIn, db: Session = Depends(get_db),
                       user_id: str = Depends(get_current_user_id)):
    thread = get_owned_or_404(db, ConversationThread, thread_id, user_id)
    if thread.status != "active" or thread.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Conversation is archived or expired")
    version = db.query(AgentVersion).filter(AgentVersion.id == thread.agent_version_id,
                                            AgentVersion.user_id == user_id).one()
    agent = get_owned_or_404(db, Agent, thread.agent_id, user_id)
    run_input = {**body.variables, "message": body.message}
    if version.input_schema is not None:
        try: jsonschema.validate(run_input, version.input_schema.json_schema)
        except jsonschema.ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Input failed schema validation: {exc.message}") from exc
    service = ConversationMemoryService(db)
    try:
        context = service.build_context(thread, version)
    except (ConversationMemoryError, SecretResolutionError) as exc:
        if isinstance(exc, ConversationMemoryError):
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
        raise HTTPException(status_code=409, detail={"code": "provider_connection_invalid", "message": str(exc)}) from exc
    run = Run(agent_version_id=version.id, user_id=user_id, input=run_input, status="pending",
              runtime_engine=version.harness_config.get("runtime_engine", "direct"))
    db.add(run); db.commit(); db.refresh(run)
    await execute_run(db, run, version, agent.id, user_id, conversation_context=context.text,
                      prior_model_calls=int(context.summary_usage.get("model_calls", 0)))
    if context.summarized:
        next_step = (db.query(func.max(RunStep.step_num)).filter(RunStep.run_id == run.id).scalar() or 0) + 1
        db.add(RunStep(run_id=run.id, step_num=next_step, type="conversation_summarized",
                       detail={"summary_tokens": thread.summary_token_count,
                               "usage": context.summary_usage, "content_logged": False}))
    if context.summary_usage:
        stats = run.runtime_stats or {}
        run.runtime_stats = {**stats,
            "model_calls": int(stats.get("model_calls", 0)) + int(context.summary_usage.get("model_calls", 0)),
            "input_tokens": int(stats.get("input_tokens", 0)) + int(context.summary_usage.get("input_tokens", 0)),
            "output_tokens": int(stats.get("output_tokens", 0)) + int(context.summary_usage.get("output_tokens", 0)),
            "memory_summary_model_calls": context.summary_usage.get("model_calls", 0),
            "memory_summary_input_tokens": context.summary_usage.get("input_tokens", 0),
            "memory_summary_output_tokens": context.summary_usage.get("output_tokens", 0)}
        db.commit()
    messages = service.record_turn(thread, body.message, run)
    return {"run": {"id": run.id, "agent_version_id": run.agent_version_id, "status": run.status,
                    "input": run.input, "output": run.output, "started_at": run.started_at,
                    "completed_at": run.completed_at, "citations": run.citations or [],
                    "grounding_status": run.grounding_status, "retrieval_stats": run.retrieval_stats or {},
                    "runtime_engine": run.runtime_engine, "runtime_stats": run.runtime_stats or {}},
            "messages": [message_out(item) for item in messages],
            "memory": {"context_tokens": context.token_count, "summarized": context.summarized,
                       "expires_at": thread.expires_at}}


@router.post("/conversations/{thread_id}/clear-memory", status_code=204)
def clear_memory(thread_id: str, db: Session = Depends(get_db),
                 user_id: str = Depends(get_current_user_id)):
    row = get_owned_or_404(db, ConversationThread, thread_id, user_id)
    db.query(ConversationMessage).filter(ConversationMessage.thread_id == thread_id,
                                         ConversationMessage.user_id == user_id).delete()
    row.summary = {}; row.summarized_through_message_id = None
    row.summary_token_count = row.message_token_count = 0
    row.updated_at = datetime.now(timezone.utc); row.expires_at = expires_at(); db.commit()
