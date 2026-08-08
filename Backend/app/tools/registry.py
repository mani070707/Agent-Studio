from app.tools import calculator, search_documents, url_fetch, web_search

# Each module must expose NAME, DESCRIPTION, INPUT_SCHEMA, OUTPUT_SCHEMA, and run(args, context) -> dict.
_MODULES = [calculator, url_fetch, web_search, search_documents]


def definitions() -> list[dict]:
    """Built-in tools are application code, not mutable database seed data."""
    return [
        {
            "name": module.NAME,
            "description": module.DESCRIPTION,
            "input_schema": module.INPUT_SCHEMA,
            "output_schema": module.OUTPUT_SCHEMA,
        }
        for module in _MODULES
    ]

PLATFORM_TOOLS = {m.NAME: m for m in _MODULES}


def invoke(tool_name: str, args: dict, context: dict | None = None) -> dict:
    if tool_name not in PLATFORM_TOOLS:
        raise KeyError(f"Unknown platform tool: {tool_name}")
    return PLATFORM_TOOLS[tool_name].run(args, context)
