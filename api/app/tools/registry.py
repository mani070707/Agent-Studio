from app.tools import calculator, search_documents, url_fetch, web_search

# Each module must expose NAME, DESCRIPTION, INPUT_SCHEMA, OUTPUT_SCHEMA, and run(args, context) -> dict.
_MODULES = [calculator, url_fetch, web_search, search_documents]

PLATFORM_TOOLS = {m.NAME: m for m in _MODULES}


def invoke(tool_name: str, args: dict, context: dict | None = None) -> dict:
    if tool_name not in PLATFORM_TOOLS:
        raise KeyError(f"Unknown platform tool: {tool_name}")
    return PLATFORM_TOOLS[tool_name].run(args, context)


def sync_to_db(db) -> None:
    """Upsert each registered tool's declared schema into platform_tool — keeps the DB row
    in sync with what code actually exists rather than hand-maintained separately."""
    from app.db.models import PlatformTool

    for module in _MODULES:
        existing = db.query(PlatformTool).filter(PlatformTool.name == module.NAME).first()
        if existing:
            existing.description = module.DESCRIPTION
            existing.input_schema = module.INPUT_SCHEMA
            existing.output_schema = module.OUTPUT_SCHEMA
        else:
            db.add(
                PlatformTool(
                    name=module.NAME,
                    description=module.DESCRIPTION,
                    input_schema=module.INPUT_SCHEMA,
                    output_schema=module.OUTPUT_SCHEMA,
                )
            )
    db.commit()
