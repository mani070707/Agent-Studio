import jsonschema
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Agent, AgentVersion, Run, RunStep
from app.db.session import get_db
from app.runs.executor import execute_run, preflight_for_run

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


class RunStepOut(BaseModel):
    step_num: int
    type: str
    detail: dict


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
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id, AgentVersion.agent_id == agent_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Agent version not found")

    if version.input_schema is not None:
        try:
            jsonschema.validate(body.input, version.input_schema.json_schema)
        except jsonschema.ValidationError as exc:
            raise HTTPException(status_code=400, detail=f"Input failed schema validation: {exc}") from exc

    run = Run(agent_version_id=version_id, user_id=user_id, input=body.input, status="pending")
    db.add(run)
    db.commit()
    db.refresh(run)

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


@router.get("/runs/{run_id}/steps", response_model=list[RunStepOut])
def get_run_steps(run_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, Run, run_id, user_id)
    return db.query(RunStep).filter(RunStep.run_id == run_id).order_by(RunStep.step_num).all()
