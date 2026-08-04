import httpx

DUCKDUCKGO_URL = "https://api.duckduckgo.com/"


def search(query: str) -> dict:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(
            DUCKDUCKGO_URL,
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        response.raise_for_status()
        data = response.json()

    related = [
        {"text": topic["Text"], "url": topic["FirstURL"]}
        for topic in data.get("RelatedTopics", [])
        if isinstance(topic, dict) and topic.get("FirstURL")
    ]
    return {
        "abstract": data.get("AbstractText", ""),
        "abstract_url": data.get("AbstractURL", ""),
        "related_topics": related[:5],
    }


NAME = "web_search"
DESCRIPTION = "Searches the web via DuckDuckGo's free Instant Answer API (no key required)."
INPUT_SCHEMA = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "abstract": {"type": "string"},
        "abstract_url": {"type": "string"},
        "related_topics": {"type": "array"},
    },
}


def run(args: dict, context: dict | None = None) -> dict:
    return search(args["query"])
