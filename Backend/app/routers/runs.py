import jsonschema
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from typing import Literal
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.core.config import settings
from app.db.models import (Agent, AgentVersion, Run, RunStep, WorkflowApproval,
                           WorkflowExecution, WorkflowJob, WorkflowNodeEvent)
from app.db.session import get_db
from app.runs.executor import execute_run, preflight_for_run
from app.observability.service import emit

router = APIRouter(tags=["runs"])


class RunIn(BaseModel):
    input: dict = {}


class RunOut(BaseModel):
    id: str
    agent_version_id: str
    status: str
    input: dict
    output: dict | None
    started_at: str | None
    completed_at: str | None
    citations: list[dict] = []
    grounding_status: str | None = None
    retrieval_stats: dict = {}
    runtime_engine: str = "direct"
    runtime_stats: dict = {}


class RunStepOut(BaseModel):
    step_num: int
    type: str
    detail: dict


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = ""


@router.get("/runtime-engines")
def runtime_engines():
    return [
        {"id": "direct", "name": "Direct SDK", "description": "Framework-free provider adapters."},
        {"id": "langchain", "name": "LangChain LCEL",
         "description": "LangChain prompts, messages, tools, retriever and runnable composition."},
        {"id": "langgraph", "name": "LangGraph workflow",
         "description": "Durable research graph for workflow agents, with checkpoints and approvals."},
    ]


@router.post("/agents/{agent_id}/versions/{version_id}/run/preflight")
def preflight_agent_version(
    agent_id: str,
    version_id: str,
    body: RunIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id, AgentVersion.agent_id == agent_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Agent version not found")
    return preflight_for_run(db, version, agent_id, body.input)


@router.post("/agents/{agent_id}/versions/{version_id}/run", response_model=RunOut)
async def run_agent_version(
    agent_id: str,
    version_id: str,
    body: RunIn,
    response: Response,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = get_owned_or_404(db, Agent, agent_id, user_id)
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id, AgentVersion.agent_id == agent_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Agent version not found")

    if version.input_schema is not None:
        try:
            jsonschema.validate(body.input, version.input_schema.json_schema)
        except jsonschema.ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Input failed schema validation: {exc}") from exc

    workflow = agent.agent_type == "workflow"
    run = Run(agent_version_id=version_id, user_id=user_id, input=body.input,
              status="queued" if workflow else "pending", runtime_engine="langgraph" if workflow else
              version.harness_config.get("runtime_engine", "direct"))
    db.add(run)
    db.flush()
    if workflow:
        if len(settings.checkpoint_encryption_key) != 32:
            raise HTTPException(status_code=503, detail="Workflow checkpoint encryption is not configured")
        now = datetime.now(timezone.utc)
        db.add(WorkflowExecution(run_id=run.id, user_id=user_id, thread_id=str(uuid.uuid4()),
            checkpoint_expires_at=now + timedelta(days=settings.workflow_checkpoint_retention_days),
            created_at=now, updated_at=now))
        db.add(WorkflowJob(run_id=run.id, user_id=user_id, status="queued", available_at=now,
                           created_at=now, updated_at=now))
        emit(db, user_id=user_id, resource_type="workflow", resource_id=run.id,
             event_type="queued", payload={"agent_version_id": version_id})
    db.commit()
    db.refresh(run)

    if workflow:
        response.status_code = 202
        return run

    # Runs synchronously (a few seconds to ~1 min for a typical tool-calling loop) — no queue/
    # worker infra is provisioned for this deployment, so the HTTP request itself blocks and
    # returns the completed run. run_step rows are already persisted for the trace view by
    # the time this returns, so GET .../steps works immediately after.
    await execute_run(db, run, version, agent_id, user_id)
    db.refresh(run)
    return run


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    agent_id: str | None = None,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    query = db.query(Run).filter(Run.user_id == user_id)
    if agent_id:
        query = query.join(AgentVersion).filter(AgentVersion.agent_id == agent_id)
    return query.order_by(Run.id.desc()).all()


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return get_owned_or_404(db, Run, run_id, user_id)


@router.get("/runs/{run_id}/graph")
def get_run_graph(run_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Run, run_id, user_id)
    execution = db.query(WorkflowExecution).filter(WorkflowExecution.run_id == run_id,
                                                   WorkflowExecution.user_id == user_id).first()
    if not execution: raise HTTPException(status_code=404, detail="Workflow graph not found")
    events = db.query(WorkflowNodeEvent).filter(WorkflowNodeEvent.run_id == run_id,
                                                WorkflowNodeEvent.user_id == user_id).order_by(WorkflowNodeEvent.started_at).all()
    from app.workflows.graph import EDGES, NODES
    return {"graph_version": execution.graph_version, "current_node": execution.current_node,
            "status": execution.status, "resumable": execution.resumable,
            "nodes": [{"id": node, "events": [{"status": event.status, "attempt": event.attempt,
                       "detail": event.detail, "started_at": event.started_at,
                       "completed_at": event.completed_at} for event in events if event.node == node]} for node in NODES],
            "edges": [{"source": source, "target": target} for source, target in EDGES]}


@router.get("/runs/{run_id}/approvals")
def list_approvals(run_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Run, run_id, user_id)
    return db.query(WorkflowApproval).filter(WorkflowApproval.run_id == run_id,
                                             WorkflowApproval.user_id == user_id).order_by(WorkflowApproval.created_at).all()


@router.post("/runs/{run_id}/approvals/{approval_id}")
def decide_approval(run_id: str, approval_id: str, body: ApprovalDecisionIn,
                    db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    run = get_owned_or_404(db, Run, run_id, user_id)
    execution = db.query(WorkflowExecution).filter(WorkflowExecution.run_id == run_id,
                                                   WorkflowExecution.user_id == user_id).first()
    approval = db.query(WorkflowApproval).filter(WorkflowApproval.id == approval_id,
        WorkflowApproval.run_id == run_id, WorkflowApproval.user_id == user_id,
        WorkflowApproval.status == "pending").first()
    if not execution or not approval: raise HTTPException(status_code=404, detail="Pending approval not found")
    now = datetime.now(timezone.utc)
    if approval.expires_at < now: raise HTTPException(status_code=409, detail="Approval has expired")
    approval.status = "approved" if body.decision == "approve" else "rejected"
    approval.reason = body.reason[:1000]; approval.decided_by = user_id; approval.decided_at = now
    execution.pending_interrupt = {**execution.pending_interrupt,
        "resume": {"decision": body.decision, "reason": approval.reason}}
    execution.status = run.status = "queued"; execution.resumable = True; execution.updated_at = now
    job = db.query(WorkflowJob).filter(WorkflowJob.run_id == run_id).one()
    job.status = "queued"; job.available_at = now; job.lease_owner = job.lease_until = None; job.updated_at = now
    emit(db, user_id=user_id, resource_type="approval", resource_id=approval.id,
         event_type=approval.status, payload={"run_id": run_id, "tool_type": approval.tool_type})
    emit(db, user_id=user_id, resource_type="workflow", resource_id=run_id,
         event_type="resumed", payload={"decision": body.decision})
    db.commit(); return {"status": approval.status}


@router.post("/runs/{run_id}/resume", response_model=RunOut)
def resume_workflow(run_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    run = get_owned_or_404(db, Run, run_id, user_id)
    execution = db.query(WorkflowExecution).filter(WorkflowExecution.run_id == run_id,
                                                   WorkflowExecution.user_id == user_id).first()
    if not execution or run.status != "failed" or not execution.resumable:
        raise HTTPException(status_code=409, detail="Workflow is not resumable")
    job = db.query(WorkflowJob).filter(WorkflowJob.run_id == run_id).one(); now = datetime.now(timezone.utc)
    run.status = execution.status = job.status = "queued"; job.available_at = now
    job.lease_owner = job.lease_until = None; execution.updated_at = job.updated_at = now
    db.commit(); db.refresh(run); return run


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_workflow(run_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    run = get_owned_or_404(db, Run, run_id, user_id)
    execution = db.query(WorkflowExecution).filter(WorkflowExecution.run_id == run_id,
                                                   WorkflowExecution.user_id == user_id).first()
    if not execution or run.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Workflow cannot be cancelled")
    now = datetime.now(timezone.utc); run.status = execution.status = "cancelled"; run.completed_at = now.isoformat()
    job = db.query(WorkflowJob).filter(WorkflowJob.run_id == run_id).one(); job.status = "cancelled"
    execution.resumable = False; execution.updated_at = job.updated_at = now
    emit(db, user_id=user_id, resource_type="workflow", resource_id=run_id,
         event_type="cancelled", payload={})
    db.commit(); db.refresh(run); return run


@router.get("/runs/{run_id}/steps", response_model=list[RunStepOut])
def get_run_steps(run_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Run, run_id, user_id)
    return db.query(RunStep).filter(RunStep.run_id == run_id).order_by(RunStep.step_num).all()
