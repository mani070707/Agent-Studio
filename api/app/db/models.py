import uuid
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


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
    agent_id: Mapped[str] = mapped_column(String, index=True)
    filename: Mapped[str] = mapped_column(String)
    storage_path: Mapped[str] = mapped_column(String)
    extracted_text: Mapped[str] = mapped_column(Text, default="")


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

    skill: Mapped["Skill"] = relationship("Skill", foreign_keys=[skill_id])
    output_schema: Mapped["SchemaEntry"] = relationship("SchemaEntry", foreign_keys=[output_schema_id])
    input_schema: Mapped[Optional["SchemaEntry"]] = relationship("SchemaEntry", foreign_keys=[input_schema_id])


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


class RunStep(Base):
    __tablename__ = "run_step"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String, ForeignKey("run.id"), index=True)
    step_num: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String)
    detail: Mapped[dict] = mapped_column(JSON)


class EvaluationDataset(Base):
    __tablename__ = "evaluation_dataset"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_id: Mapped[str] = mapped_column(String, ForeignKey("agent.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    threshold: Mapped[float] = mapped_column(Float, default=0.9)


class EvaluationCase(Base):
    __tablename__ = "evaluation_case"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    dataset_id: Mapped[str] = mapped_column(String, ForeignKey("evaluation_dataset.id"), index=True)
    input: Mapped[dict] = mapped_column(JSON)
    expected_output: Mapped[dict] = mapped_column(JSON)
    compare_fields: Mapped[list] = mapped_column(JSON, default=list)


class EvaluationRun(Base):
    __tablename__ = "evaluation_run"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    agent_version_id: Mapped[str] = mapped_column(String, ForeignKey("agent_version.id"), index=True)
    dataset_id: Mapped[str] = mapped_column(String, ForeignKey("evaluation_dataset.id"))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="pending")
