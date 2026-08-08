from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.crud_helpers import get_owned_or_404
from app.db.models import McpServer, McpTool
from app.db.session import get_db
from app.mcp_client.client import list_tools

router = APIRouter(prefix="/mcp-servers", tags=["mcp"])


class McpServerIn(BaseModel):
    name: str
    url: str
    secret_ref: str | None = None


class McpServerOut(McpServerIn):
    id: str


class McpToolOut(BaseModel):
    id: str
    tool_name: str
    input_schema: dict
    output_schema: dict


@router.get("", response_model=list[McpServerOut])
def list_mcp_servers(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return db.query(McpServer).filter(McpServer.user_id == user_id).all()


@router.post("", response_model=McpServerOut, status_code=201)
async def create_mcp_server(
    body: McpServerIn, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    server = McpServer(user_id=user_id, **body.model_dump())
    db.add(server)
    db.commit()
    db.refresh(server)
    await _sync_tools(db, server)
    return server


@router.post("/{server_id}/sync", response_model=list[McpToolOut])
async def sync_mcp_server(
    server_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)
):
    server = get_owned_or_404(db, McpServer, server_id, user_id)
    return await _sync_tools(db, server)


@router.get("/{server_id}/tools", response_model=list[McpToolOut])
def list_mcp_tools(server_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    get_owned_or_404(db, McpServer, server_id, user_id)  # ownership check
    return db.query(McpTool).filter(McpTool.mcp_server_id == server_id).all()


@router.delete("/{server_id}", status_code=204)
def delete_mcp_server(server_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    server = get_owned_or_404(db, McpServer, server_id, user_id)
    db.query(McpTool).filter(McpTool.mcp_server_id == server_id).delete()
    db.delete(server)
    db.commit()


async def _sync_tools(db: Session, server: McpServer) -> list[McpTool]:
    """Discover a server's tools via tools/list and upsert mcp_tool rows to match — the
    registry stays in sync with what the server actually exposes, never hand-entered."""
    try:
        discovered = await list_tools(server.url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach MCP server: {exc}") from exc

    db.query(McpTool).filter(McpTool.mcp_server_id == server.id).delete()
    rows = [
        McpTool(
            mcp_server_id=server.id,
            tool_name=tool["name"],
            input_schema=tool["input_schema"],
            output_schema=tool.get("output_schema") or {"type": "object"},
        )
        for tool in discovered
    ]
    db.add_all(rows)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows
