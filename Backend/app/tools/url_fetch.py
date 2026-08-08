import httpx

from app.core.ssrf_guard import UnsafeUrlError, assert_safe_url

MAX_BYTES = 200_000


def fetch(url: str, _max_redirects: int = 3) -> str:
    # Redirects are followed manually (not via httpx's follow_redirects) so every hop is
    # re-validated against the SSRF check — a public URL redirecting to an internal one
    # would otherwise bypass assert_safe_url entirely.
    with httpx.Client(follow_redirects=False, timeout=10.0) as client:
        for _ in range(_max_redirects + 1):
            assert_safe_url(url)
            response = client.get(url)
            if response.is_redirect and response.headers.get("location"):
                url = str(response.next_request.url) if response.next_request else response.headers["location"]
                continue
            response.raise_for_status()
            return response.text[:MAX_BYTES]
    raise UnsafeUrlError("Too many redirects")


NAME = "url_fetch"
DESCRIPTION = "Fetches the text content of a public HTTP(S) URL."
INPUT_SCHEMA = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}
OUTPUT_SCHEMA = {"type": "object", "properties": {"content": {"type": "string"}}}


def run(args: dict, context: dict | None = None) -> dict:
    return {"content": fetch(args["url"])}
