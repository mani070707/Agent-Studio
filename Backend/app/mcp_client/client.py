from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def list_tools(server_url: str) -> list[dict]:
    """Connect to an MCP server over streamable HTTP and return its declared tools."""
    async with streamable_http_client(server_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": tool.inputSchema or {"type": "object"},
                }
                for tool in result.tools
            ]


async def call_tool(server_url: str, tool_name: str, arguments: dict) -> dict:
    """Call a tool on a registered MCP server and return its result content."""
    async with streamable_http_client(server_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.isError:
                raise RuntimeError(f"MCP tool '{tool_name}' returned an error: {result.content}")
            text_parts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
            return {"content": "\n".join(text_parts) if text_parts else str(result.content)}
