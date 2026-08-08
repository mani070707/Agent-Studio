from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Connector, KnowledgeBase, McpTool, ProviderConnection, SchemaEntry, Skill
from app.modules.providers.domain import ProviderCatalog
from app.tools.registry import PLATFORM_TOOLS


def validate_harness_selections(
    db: Session,
    user_id: str,
    *,
    skill_id: str,
    input_schema_id: str | None,
    output_schema_id: str,
    tool_allowlist: list[str],
    mcp_tool_allowlist: list[str],
    connector_allowlist: list[str],
    skill_allowlist: list[str],
    runtime_model: dict,
    knowledge_base_ids: list[str] | None = None,
) -> None:
    """Reject a harness config referencing anything not in the registry or not owned by
    this user — enforced server-side, not just hidden in the UI."""
    if not db.query(Skill).filter(Skill.id == skill_id, Skill.user_id == user_id).first():
        raise HTTPException(status_code=400, detail=f"skill_id '{skill_id}' not found")

    if not db.query(SchemaEntry).filter(
        SchemaEntry.id == output_schema_id, SchemaEntry.user_id == user_id, SchemaEntry.kind == "output"
    ).first():
        raise HTTPException(status_code=400, detail=f"output_schema_id '{output_schema_id}' not found")

    if input_schema_id and not db.query(SchemaEntry).filter(
        SchemaEntry.id == input_schema_id, SchemaEntry.user_id == user_id, SchemaEntry.kind == "input"
    ).first():
        raise HTTPException(status_code=400, detail=f"input_schema_id '{input_schema_id}' not found")

    known_platform_tools = set(PLATFORM_TOOLS)
    for name in tool_allowlist:
        if name not in known_platform_tools:
            raise HTTPException(status_code=400, detail=f"Unknown platform tool: '{name}'")

    for mcp_tool_id in mcp_tool_allowlist:
        row = (
            db.query(McpTool)
            .join(McpTool.mcp_server)
            .filter(McpTool.id == mcp_tool_id)
            .first()
        )
        if not row or row.mcp_server.user_id != user_id:
            raise HTTPException(status_code=400, detail=f"Unknown mcp_tool_id: '{mcp_tool_id}'")

    for connector_id in connector_allowlist:
        if not db.query(Connector).filter(Connector.id == connector_id, Connector.user_id == user_id).first():
            raise HTTPException(status_code=400, detail=f"Unknown connector_id: '{connector_id}'")

    for allowed_skill_id in skill_allowlist:
        if not db.query(Skill).filter(Skill.id == allowed_skill_id, Skill.user_id == user_id).first():
            raise HTTPException(status_code=400, detail=f"Unknown skill_id in skill_allowlist: '{allowed_skill_id}'")

    provider = runtime_model.get("provider")
    try:
        definition = ProviderCatalog().require(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if runtime_model.get("model_id") not in {model.id for model in definition.models}:
        raise HTTPException(status_code=400, detail="Selected model is not in the provider capability catalog")
    connection_id = runtime_model.get("provider_connection_id")
    legacy_ref = runtime_model.get("api_key_secret_ref")
    if not connection_id and not legacy_ref:
        raise HTTPException(status_code=400, detail="A provider connection or legacy secret reference is required")
    if connection_id:
        connection = db.query(ProviderConnection).filter(
            ProviderConnection.id == connection_id, ProviderConnection.user_id == user_id
        ).first()
        if not connection or connection.provider != provider:
            raise HTTPException(status_code=400, detail="Provider connection is unavailable or does not match")

    knowledge_base_ids = knowledge_base_ids or []
    if len(knowledge_base_ids) > 5:
        raise HTTPException(status_code=400, detail="At most five knowledge bases may be bound to one version")
    if len(set(knowledge_base_ids)) != len(knowledge_base_ids):
        raise HTTPException(status_code=400, detail="Duplicate knowledge-base bindings are not allowed")
    owned = db.query(KnowledgeBase.id).filter(
        KnowledgeBase.id.in_(knowledge_base_ids), KnowledgeBase.user_id == user_id,
        KnowledgeBase.status == "active",
    ).count() if knowledge_base_ids else 0
    if owned != len(knowledge_base_ids):
        raise HTTPException(status_code=400, detail="A selected knowledge base is unavailable or archived")
    if knowledge_base_ids and "search_documents" not in tool_allowlist:
        raise HTTPException(status_code=400, detail="Hybrid knowledge retrieval requires search_documents")
