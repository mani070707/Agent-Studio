import re

import httpx

from app.core.ssrf_guard import assert_safe_url

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _interpolate(value, variables: dict):
    if isinstance(value, str):
        return _VAR_PATTERN.sub(lambda m: str(variables.get(m.group(1), "")), value)
    if isinstance(value, dict):
        return {k: _interpolate(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, variables) for v in value]
    return value


def execute_connector(base_url: str, request_template: dict, variables: dict, secret_value: str | None) -> dict:
    all_vars = {**variables, "secret": secret_value or ""}
    method = request_template.get("method", "GET")
    path = request_template.get("path", "")
    url = base_url.rstrip("/") + path
    assert_safe_url(url)

    headers = _interpolate(request_template.get("headers", {}), all_vars)
    body = _interpolate(request_template.get("body"), all_vars)

    with httpx.Client(follow_redirects=False, timeout=15.0) as client:
        response = client.request(method, url, headers=headers, json=body)
        response.raise_for_status()
        try:
            return response.json()
        except ValueError:
            return {"raw_text": response.text[:50_000]}
