from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Connector, McpTool, PlatformTool, SchemaEntry, Skill


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

    known_platform_tools = {t.name for t in db.query(PlatformTool).all()}
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
