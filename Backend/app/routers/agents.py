from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents.validation import validate_harness_selections
from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import Agent, AgentVersion, AgentVersionKnowledgeBase, EvaluationDataset, EvaluationRun
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


class WorkflowConfig(BaseModel):
    graph_version: Literal["research_v1"] = "research_v1"
    max_plan_steps: int = 5
    max_retrieval_queries: int = 3
    max_research_cycles: int = 2
    max_repair_cycles: int = 1
    approval_policy: Literal["mcp_and_connectors"] = "mcp_and_connectors"


class HarnessConfig(BaseModel):
    runtime_engine: Literal["direct", "langchain"] = "direct"
    runtime_model: RuntimeModelConfig
    prompt_guardrails: PromptGuardrailsConfig = PromptGuardrailsConfig()
    memory: MemoryConfig = MemoryConfig()
    workflow: WorkflowConfig = WorkflowConfig()


class RetrievalConfig(BaseModel):
    mode: Literal["hybrid"] = "hybrid"
    top_k: int = 6
    max_per_document: int = 3
    standard_context_tokens: int = 2500
    free_context_tokens: int = 1200


class AgentVersionIn(BaseModel):
    harness_config: HarnessConfig
    skill_id: str
    input_schema_id: str | None = None
    output_schema_id: str
    tool_allowlist: list[str] = []
    mcp_tool_allowlist: list[str] = []
    connector_allowlist: list[str] = []
    skill_allowlist: list[str] = []
    knowledge_base_ids: list[str] = []
    retrieval_config: RetrievalConfig = RetrievalConfig()


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
    knowledge_base_ids: list[str] = []
    retrieval_config: dict


def _version_out(db: Session, version: AgentVersion) -> dict:
    data = {column.name: getattr(version, column.name) for column in AgentVersion.__table__.columns}
    data["knowledge_base_ids"] = [row.knowledge_base_id for row in db.query(AgentVersionKnowledgeBase).filter(
        AgentVersionKnowledgeBase.agent_version_id == version.id).order_by(
        AgentVersionKnowledgeBase.knowledge_base_id).all()]
    return data


def _replace_bindings(db: Session, version: AgentVersion, knowledge_base_ids: list[str]) -> None:
    db.query(AgentVersionKnowledgeBase).filter(
        AgentVersionKnowledgeBase.agent_version_id == version.id).delete()
    db.add_all([AgentVersionKnowledgeBase(agent_version_id=version.id, knowledge_base_id=base_id,
                                          user_id=version.user_id) for base_id in knowledge_base_ids])


def _validate_memory_agent(agent: Agent, body: AgentVersionIn) -> None:
    memory = body.harness_config.memory
    if memory.vector_memory_enabled and agent.agent_type != "chat":
        raise HTTPException(status_code=400, detail="Conversation memory is supported only for chat agents")
    if memory.graph_memory_enabled or memory.episodic_memory_enabled:
        raise HTTPException(status_code=400, detail="Long-term graph and episodic memory are not available")


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
    versions = (
        db.query(AgentVersion)
        .filter(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.version_number.desc())
        .all()
    )
    return [_version_out(db, version) for version in versions]


@router.post("/{agent_id}/versions", response_model=AgentVersionOut, status_code=201)
def create_agent_version(
    agent_id: str,
    body: AgentVersionIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = get_owned_or_404(db, Agent, agent_id, user_id)
    _validate_memory_agent(agent, body)

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
        knowledge_base_ids=body.knowledge_base_ids,
    )

    last_version = (
        db.query(AgentVersion)
        .filter(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.version_number.desc())
        .first()
    )
    version = AgentVersion(
        user_id=user_id,
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
        retrieval_config=body.retrieval_config.model_dump(),
    )
    db.add(version)
    db.flush()
    _replace_bindings(db, version, body.knowledge_base_ids)
    db.commit()
    db.refresh(version)
    return _version_out(db, version)


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
    return _version_out(db, version)


@router.put("/{agent_id}/versions/{version_id}", response_model=AgentVersionOut)
def update_agent_version(
    agent_id: str,
    version_id: str,
    body: AgentVersionIn,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    agent = get_owned_or_404(db, Agent, agent_id, user_id)
    _validate_memory_agent(agent, body)
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
        knowledge_base_ids=body.knowledge_base_ids,
    )

    version.harness_config = body.harness_config.model_dump()
    version.skill_id = body.skill_id
    version.input_schema_id = body.input_schema_id
    version.output_schema_id = body.output_schema_id
    version.tool_allowlist = body.tool_allowlist
    version.mcp_tool_allowlist = body.mcp_tool_allowlist
    version.connector_allowlist = body.connector_allowlist
    version.skill_allowlist = body.skill_allowlist
    version.retrieval_config = body.retrieval_config.model_dump()
    _replace_bindings(db, version, body.knowledge_base_ids)
    db.commit()
    db.refresh(version)
    return _version_out(db, version)


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
            .order_by(EvaluationRun.created_at.desc())
            .first()
        )
        dataset = db.query(EvaluationDataset).filter(EvaluationDataset.id == latest_eval.dataset_id).first() if latest_eval else None
        snapshot_updated = (latest_eval.config_snapshot or {}).get("dataset_updated_at") if latest_eval else None
        stale = bool(dataset and snapshot_updated != dataset.updated_at.isoformat())
        if not latest_eval or latest_eval.status != "passed" or stale or not all((latest_eval.gate_results or {}).values()):
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "evaluation_gate_not_passed",
                    "latestScore": latest_eval.score if latest_eval else None,
                    "staleDataset": stale,
                    "gates": latest_eval.gate_results if latest_eval else {},
                },
            )

    version.is_published = True
    version.published_at = datetime.now(timezone.utc).isoformat()
    agent.status = "active"
    db.commit()
    db.refresh(version)
    return _version_out(db, version)
