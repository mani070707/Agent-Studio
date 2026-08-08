NAME = "search_documents"
DESCRIPTION = "Searches only this agent version's bound knowledge bases and returns grounded evidence source IDs."
INPUT_SCHEMA = {"type": "object", "properties": {"query": {"type": "string", "maxLength": 4000}},
                "required": ["query"]}
OUTPUT_SCHEMA = {"type": "object", "properties": {"matches": {"type": "array"}}}


def run(args: dict, context: dict) -> dict:
    retriever = context.get("retriever")
    ledger = context.get("evidence_ledger")
    version = context.get("version")
    if not retriever or not ledger or not version:
        return {"matches": [], "warning": "No knowledge bases are bound to this agent version."}
    config = version.retrieval_config or {}
    evidence, stats = retriever.retrieve(
        version.id, context["user_id"], str(args.get("query", "")),
        top_k=int(config.get("top_k", 6)), max_per_document=int(config.get("max_per_document", 3)),
        token_budget=int(config.get("free_context_tokens" if context.get("free") else
                                    "standard_context_tokens", 1200 if context.get("free") else 2500)),
        ledger=ledger,
    )
    return {"matches": [{"source_id": item.source_id, "filename": item.filename,
                          "page_start": item.page_start, "page_end": item.page_end,
                          "excerpt": item.excerpt, "score": item.score} for item in evidence], "stats": stats}
