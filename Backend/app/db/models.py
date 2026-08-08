import uuid
from typing import Optional

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, UserDefinedType
from sqlalchemy.ext.compiler import compiles

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Vector384(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        return "vector(384)"

    def bind_processor(self, dialect):
        return lambda value: None if value is None else "[" + ",".join(str(float(item)) for item in value) + "]"


@compiles(Vector384, "sqlite")
def _compile_vector_sqlite(type_, compiler, **kw) -> str:
    return "TEXT"


class Skill(Base):
    __tablename__ = "skill"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    system_prompt: Mapped[str] = mapped_column(Text)
    user_prompt_template: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)


class SchemaEntry(Base):
    __tablename__ = "schema_entry"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # "input" | "output"
    json_schema: Mapped[dict] = mapped_column(JSON)
    version: Mapped[str] = mapped_column(String, default="1.0.0")


class UserSecret(Base):
    __tablename__ = "user_secret"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    encrypted_value: Mapped[str] = mapped_column(Text)


class ProviderConnection(Base):
    __tablename__ = "provider_connection"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    provider: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String)
    secret_ref: Mapped[str] = mapped_column(String)
    validation_status: Mapped[str] = mapped_column(String, default="unverified")
    last_validated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String)


class PlatformTool(Base):
    __tablename__ = "platform_tool"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text)
    input_schema: Mapped[dict] = mapped_column(JSON)
    output_schema: Mapped[dict] = mapped_column(JSON)


class McpServer(Base):
    __tablename__ = "mcp_server"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)
    secret_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class McpTool(Base):
    __tablename__ = "mcp_tool"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    mcp_server_id: Mapped[str] = mapped_column(String, ForeignKey("mcp_server.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String)
    input_schema: Mapped[dict] = mapped_column(JSON)
    output_schema: Mapped[dict] = mapped_column(JSON)

    mcp_server: Mapped["McpServer"] = relationship("McpServer")


class Connector(Base):
    __tablename__ = "connector"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    base_url: Mapped[str] = mapped_column(String)
    auth_secret_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    request_template: Mapped[dict] = mapped_column(JSON)


class ContentItem(Base):
    __tablename__ = "content_item"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[Optional[str]] = mapped_column(String, index=True, nullable=True)
    knowledge_base_id: Mapped[str] = mapped_column(String, index=True)
    filename: Mapped[str] = mapped_column(String)
    storage_path: Mapped[str] = mapped_column(String)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    character_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extraction_version: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    index_status: Mapped[str] = mapped_column(String, default="pending", index=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    index_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    index_error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    index_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class IngestionJob(Base):
    __tablename__ = "ingestion_job"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_item.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    lease_owner: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentChunk(Base):
    __tablename__ = "document_chunk"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    knowledge_base_id: Mapped[str] = mapped_column(String, index=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_item.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text_hash: Mapped[str] = mapped_column(String)
    embedding_model: Mapped[str] = mapped_column(String)
    index_version: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list] = mapped_column(Vector384())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IndexingJob(Base):
    __tablename__ = "indexing_job"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_item.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    lease_owner: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="active", index=True)
    legacy_agent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Agent(Base):
    __tablename__ = "agent"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    agent_type: Mapped[str] = mapped_column(String, default="task")  # task | chat | workflow
    domain: Mapped[str] = mapped_column(String, default="")
    owner: Mapped[str] = mapped_column(String, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | active
    evaluation_gate_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentVersion(Base):
    __tablename__ = "agent_version"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agent.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    harness_config: Mapped[dict] = mapped_column(JSON)
    skill_id: Mapped[str] = mapped_column(String, ForeignKey("skill.id"))
    input_schema_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("schema_entry.id"), nullable=True)
    output_schema_id: Mapped[str] = mapped_column(String, ForeignKey("schema_entry.id"))
    tool_allowlist: Mapped[list] = mapped_column(JSON, default=list)
    mcp_tool_allowlist: Mapped[list] = mapped_column(JSON, default=list)
    connector_allowlist: Mapped[list] = mapped_column(JSON, default=list)
    skill_allowlist: Mapped[list] = mapped_column(JSON, default=list)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    retrieval_config: Mapped[dict] = mapped_column(JSON, default=dict)

    skill: Mapped["Skill"] = relationship("Skill", foreign_keys=[skill_id])
    output_schema: Mapped["SchemaEntry"] = relationship("SchemaEntry", foreign_keys=[output_schema_id])
    input_schema: Mapped[Optional["SchemaEntry"]] = relationship("SchemaEntry", foreign_keys=[input_schema_id])


class AgentVersionKnowledgeBase(Base):
    __tablename__ = "agent_version_knowledge_base"

    agent_version_id: Mapped[str] = mapped_column(String, ForeignKey("agent_version.id", ondelete="CASCADE"),
                                                  primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(String, ForeignKey("knowledge_base.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AgentTrigger(Base):
    __tablename__ = "agent_trigger"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agent.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # manual | api | schedule
    auth_type: Mapped[str] = mapped_column(String, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Run(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_version_id: Mapped[str] = mapped_column(String, ForeignKey("agent_version.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    trigger_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    input: Mapped[dict] = mapped_column(JSON)
    output: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    started_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    completed_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    grounding_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    retrieval_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    runtime_engine: Mapped[str] = mapped_column(String, default="direct")
    runtime_stats: Mapped[dict] = mapped_column(JSON, default=dict)


class RunStep(Base):
    __tablename__ = "run_step"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("run.id"), index=True)
    step_num: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String)
    detail: Mapped[dict] = mapped_column(JSON)


class ConversationThread(Base):
    __tablename__ = "conversation_thread"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agent.id", ondelete="CASCADE"), index=True)
    agent_version_id: Mapped[str] = mapped_column(String, ForeignKey("agent_version.id"), index=True)
    title: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="active")
    memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    summarized_through_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    summary_token_count: Mapped[int] = mapped_column(Integer, default=0)
    message_token_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ConversationMessage(Base):
    __tablename__ = "conversation_message"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    thread_id: Mapped[str] = mapped_column(String, ForeignKey("conversation_thread.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[dict] = mapped_column(JSON)
    run_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("run.id"), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ActivityEvent(Base):
    __tablename__ = "activity_event"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    resource_type: Mapped[str] = mapped_column(String, index=True)
    resource_id: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    trace_id: Mapped[str] = mapped_column(String, index=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeat"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    worker_type: Mapped[str] = mapped_column(String, index=True)
    instance_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="online")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WorkflowExecution(Base):
    __tablename__ = "workflow_execution"
    run_id: Mapped[str] = mapped_column(String, ForeignKey("run.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    thread_id: Mapped[str] = mapped_column(String, unique=True)
    graph_version: Mapped[str] = mapped_column(String, default="research_v1")
    current_node: Mapped[str] = mapped_column(String, default="prepare")
    status: Mapped[str] = mapped_column(String, default="queued")
    pending_interrupt: Mapped[dict] = mapped_column(JSON, default=dict)
    resumable: Mapped[bool] = mapped_column(Boolean, default=False)
    checkpoint_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WorkflowJob(Base):
    __tablename__ = "workflow_job"
    run_id: Mapped[str] = mapped_column(String, ForeignKey("run.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    lease_owner: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WorkflowApproval(Base):
    __tablename__ = "workflow_approval"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("run.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    tool_name: Mapped[str] = mapped_column(String)
    tool_type: Mapped[str] = mapped_column(String)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    arguments_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    reason: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkflowNodeEvent(Base):
    __tablename__ = "workflow_node_event"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("run.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    node: Mapped[str] = mapped_column(String)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationDataset(Base):
    __tablename__ = "evaluation_dataset"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agent.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    threshold: Mapped[float] = mapped_column(Float, default=0.9)
    retrieval_recall_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    citation_precision_threshold: Mapped[float] = mapped_column(Float, default=1.0)
    grounding_threshold: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EvaluationCase(Base):
    __tablename__ = "evaluation_case"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(String, ForeignKey("evaluation_dataset.id"), index=True)
    input: Mapped[dict] = mapped_column(JSON)
    expected_output: Mapped[dict] = mapped_column(JSON)
    compare_fields: Mapped[list] = mapped_column(JSON, default=list)
    expected_document_ids: Mapped[list] = mapped_column(JSON, default=list)
    expected_chunk_ids: Mapped[list] = mapped_column(JSON, default=list)
    retrieval_k: Mapped[int] = mapped_column(Integer, default=6)


class EvaluationRun(Base):
    __tablename__ = "evaluation_run"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    agent_version_id: Mapped[str] = mapped_column(String, ForeignKey("agent_version.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(String, ForeignKey("evaluation_dataset.id"))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="queued")
    completed_cases: Mapped[int] = mapped_column(Integer, default=0)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    gate_results: Mapped[dict] = mapped_column(JSON, default=dict)
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    dataset_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    lease_owner: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lease_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationCaseResult(Base):
    __tablename__ = "evaluation_case_result"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    evaluation_run_id: Mapped[str] = mapped_column(String, ForeignKey("evaluation_run.id", ondelete="CASCADE"), index=True)
    evaluation_case_id: Mapped[str] = mapped_column(String)
    run_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("run.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="completed")
    retrieved_sources: Mapped[list] = mapped_column(JSON, default=list)
    expected_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    field_mismatches: Mapped[list] = mapped_column(JSON, default=list)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
