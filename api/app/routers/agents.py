from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.validation import validate_harness_selections
from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Agent, AgentVersion, EvaluationRun
from app.db.session import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentIn(BaseModel):
    name: str
    agent_type: Literal["task", "chat", "workflow"] = "task"
    domain: str = ""
    owner: str = ""
    tags: list[str] = []
    description: str = ""


class AgentOut(AgentIn):
    id: str
    status: str
    evaluation_gate_enabled: bool


class AgentUpdateIn(BaseModel):
    name: str | None = None
    domain: str | None = None
    owner: str | None = None
    tags: list[str] | None = None
    description: str | None = None
    evaluation_gate_enabled: bool | None = None


class RuntimeModelConfig(BaseModel):
    provider: Literal["gemini", "groq", "openrouter", "anthropic", "openai"]
    model_id: str
    temperature: float = 0
    max_tokens: int = 4096
    timeout_ms: int = 300000
    api_key_secret_ref: str | None = None
    provider_connection_id: str | None = None
    usage_tier: Literal["free", "standard"] = "standard"


class PromptGuardrailsConfig(BaseModel):
    role: str = ""
    goal: str = ""
    guardrail_profile: str = "standard"
    context_mode: Literal["minimal", "standard", "full"] = "minimal"


class MemoryConfig(BaseModel):
    vector_memory_enabled: bool = False
    graph_memory_enabled: bool = False
    episodic_memory_enabled: bool = False


class HarnessConfig(BaseModel):
    runtime_model: RuntimeModelConfig
    prompt_guardrails: PromptGuardrailsConfig = PromptGuardrailsConfig()
    memory: MemoryConfig = MemoryConfig()


class AgentVersionIn(BaseModel):
    harness_config: HarnessConfig
    skill_id: str
    input_schema_id: str | None = None
    output_schema_id: str
    tool_allowlist: list[str] = []
    mcp_tool_allowlist: list[str] = []
    connector_allowlist: list[str] = []
    skill_allowlist: list[str] = []


class AgentVersionOut(BaseModel):
    id: str
    agent_id: str
    version_number: int
    harness_config: dict
    skill_id: str
    input_schema_id: str | None
    output_schema_id: str
    tool_allowlist: list[str]
    mcp_tool_allowlist: list[str]
    connector_allowlist: list[str]
    skill_allowlist: list[str]
    is_published: bool
    published_at: str | None


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return db.query(Agent).filter(Agent.user_id == user_id).all()


@router.post("", response_model=AgentOut, status_code=201)
def create_agent(body: AgentIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    agent = Agent(user_id=user_id, **body.model_dump())
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return get_owned_or_404(db, Agent, agent_id, user_id)


@router.put("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: str,
    body: AgentUpdateIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = get_owned_or_404(db, Agent, agent_id, user_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    agent = get_owned_or_404(db, Agent, agent_id, user_id)
    db.query(AgentVersion).filter(AgentVersion.agent_id == agent_id).delete()
    db.delete(agent)
    db.commit()


@router.get("/{agent_id}/versions", response_model=list[AgentVersionOut])
def list_agent_versions(
    agent_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    return (
        db.query(AgentVersion)
        .filter(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.version_number.desc())
        .all()
    )


@router.post("/{agent_id}/versions", response_model=AgentVersionOut, status_code=201)
def create_agent_version(
    agent_id: str,
    body: AgentVersionIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = get_owned_or_404(db, Agent, agent_id, user_id)

    existing_draft = (
        db.query(AgentVersion)
        .filter(AgentVersion.agent_id == agent_id, AgentVersion.is_published.is_(False))
        .first()
    )
    if existing_draft:
        raise HTTPException(
            status_code=409,
            detail=f"A draft version already exists (id={existing_draft.id}) — edit or publish it "
            "before creating another.",
        )

    validate_harness_selections(
        db,
        user_id,
        skill_id=body.skill_id,
        input_schema_id=body.input_schema_id,
        output_schema_id=body.output_schema_id,
        tool_allowlist=body.tool_allowlist,
        mcp_tool_allowlist=body.mcp_tool_allowlist,
        connector_allowlist=body.connector_allowlist,
        skill_allowlist=body.skill_allowlist,
        runtime_model=body.harness_config.runtime_model.model_dump(),
    )

    last_version = (
        db.query(AgentVersion)
        .filter(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.version_number.desc())
        .first()
    )
    version = AgentVersion(
        agent_id=agent_id,
        version_number=(last_version.version_number + 1) if last_version else 1,
        harness_config=body.harness_config.model_dump(),
        skill_id=body.skill_id,
        input_schema_id=body.input_schema_id,
        output_schema_id=body.output_schema_id,
        tool_allowlist=body.tool_allowlist,
        mcp_tool_allowlist=body.mcp_tool_allowlist,
        connector_allowlist=body.connector_allowlist,
        skill_allowlist=body.skill_allowlist,
        runtime_model=body.harness_config.runtime_model.model_dump(),
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


@router.get("/{agent_id}/versions/{version_id}", response_model=AgentVersionOut)
def get_agent_version(
    agent_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id, AgentVersion.agent_id == agent_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Agent version not found")
    return version


@router.put("/{agent_id}/versions/{version_id}", response_model=AgentVersionOut)
def update_agent_version(
    agent_id: str,
    version_id: str,
    body: AgentVersionIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    get_owned_or_404(db, Agent, agent_id, user_id)
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id, AgentVersion.agent_id == agent_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Agent version not found")
    if version.is_published:
        raise HTTPException(status_code=409, detail="Published versions are immutable — create a new draft")

    validate_harness_selections(
        db,
        user_id,
        skill_id=body.skill_id,
        input_schema_id=body.input_schema_id,
        output_schema_id=body.output_schema_id,
        tool_allowlist=body.tool_allowlist,
        mcp_tool_allowlist=body.mcp_tool_allowlist,
        connector_allowlist=body.connector_allowlist,
        skill_allowlist=body.skill_allowlist,
        runtime_model=body.harness_config.runtime_model.model_dump(),
    )

    version.harness_config = body.harness_config.model_dump()
    version.skill_id = body.skill_id
    version.input_schema_id = body.input_schema_id
    version.output_schema_id = body.output_schema_id
    version.tool_allowlist = body.tool_allowlist
    version.mcp_tool_allowlist = body.mcp_tool_allowlist
    version.connector_allowlist = body.connector_allowlist
    version.skill_allowlist = body.skill_allowlist
    db.commit()
    db.refresh(version)
    return version


@router.post("/{agent_id}/versions/{version_id}/publish", response_model=AgentVersionOut)
def publish_agent_version(
    agent_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = get_owned_or_404(db, Agent, agent_id, user_id)
    version = db.query(AgentVersion).filter(AgentVersion.id == version_id, AgentVersion.agent_id == agent_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Agent version not found")
    if version.is_published:
        raise HTTPException(status_code=409, detail="Version is already published")

    if agent.evaluation_gate_enabled:
        latest_eval = (
            db.query(EvaluationRun)
            .filter(EvaluationRun.agent_version_id == version_id)
            .order_by(EvaluationRun.id.desc())
            .first()
        )
        if not latest_eval or latest_eval.status != "passed":
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "evaluation_gate_not_passed",
                    "latestScore": latest_eval.score if latest_eval else None,
                },
            )

    version.is_published = True
    version.published_at = datetime.now(timezone.utc).isoformat()
    agent.status = "active"
    db.commit()
    db.refresh(version)
    return version
