from app.db.models import ContentItem

NAME = "search_documents"
DESCRIPTION = (
    "Searches this agent's uploaded documents for text matching a query and returns matching excerpts."
)
INPUT_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
OUTPUT_SCHEMA = {"type": "object", "properties": {"matches": {"type": "array"}}}


def run(args: dict, context: dict) -> dict:
    db = context["db"]
    agent_id = context["agent_id"]
    query = args["query"].lower()

    items = db.query(ContentItem).filter(ContentItem.agent_id == agent_id).all()
    matches = []
    for item in items:
        text = item.extracted_text or ""
        idx = text.lower().find(query)
        if idx == -1:
            continue
        start, end = max(0, idx - 200), min(len(text), idx + 200)
        matches.append({"filename": item.filename, "excerpt": text[start:end]})
    return {"matches": matches[:10]}
