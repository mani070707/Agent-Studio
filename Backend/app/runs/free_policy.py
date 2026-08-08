import re
import time
from dataclasses import dataclass

FREE_LIMITS = {
    "model_calls": 4,
    "tool_calls": 3,
    "iterations": 4,
    "input_tokens": 16_000,
    "output_tokens_per_call": 2_048,
    "wall_time_seconds": 90,
}

_NUMBERED_TASK = re.compile(r"(?m)^\s*(?:\d+[.)]|[-*])\s+\S")


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def build_preflight(runtime_model: dict, system_prompt: str, user_prompt: str, run_input: dict,
                    selected_tools: int, document_count: int = 0) -> dict:
    free = runtime_model.get("usage_tier", "standard") == "free"
    estimated_tokens = estimate_tokens(system_prompt + "\n" + user_prompt)
    listed_tasks = len(_NUMBERED_TASK.findall(user_prompt))
    collection_tasks = max((len(value) for value in run_input.values() if isinstance(value, list)), default=0)
    likely_subtasks = max(1, listed_tasks, collection_tasks)
    warnings = []
    if free and estimated_tokens > FREE_LIMITS["input_tokens"]:
        warnings.append("Rendered prompts exceed the free input-token budget.")
    if free and likely_subtasks > 3:
        warnings.append(f"Approximately {likely_subtasks} subtasks were detected; the run may return partial work.")
    if free and selected_tools > FREE_LIMITS["tool_calls"]:
        warnings.append("More tools are enabled than the free run can call.")
    if free and document_count > 3:
        warnings.append("Document context may consume most of the free prompt budget.")
    return {
        "usage_tier": "free" if free else "standard",
        "estimated_input_tokens": estimated_tokens,
        "likely_subtasks": likely_subtasks,
        "selected_tools": selected_tools,
        "document_count": document_count,
        "limits": FREE_LIMITS if free else {"iterations": 15},
        "warnings": warnings,
        "high_complexity": bool(warnings),
    }


class BudgetExceeded(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass
class BudgetTracker:
    free: bool
    started: float = 0
    model_calls: int = 0
    tool_calls: int = 0
    iterations: int = 0

    def __post_init__(self):
        self.started = time.monotonic()

    def before_model_call(self):
        self._check_time()
        if self.free and self.model_calls >= FREE_LIMITS["model_calls"]:
            raise BudgetExceeded("FREE_MODEL_CALL_BUDGET", "The free model-call budget was exhausted.")
        self.model_calls += 1

    def before_tool_call(self):
        self._check_time()
        if self.free and self.tool_calls >= FREE_LIMITS["tool_calls"]:
            raise BudgetExceeded("FREE_TOOL_CALL_BUDGET", "The free tool-call budget was exhausted.")
        self.tool_calls += 1

    def before_iteration(self):
        self._check_time()
        limit = FREE_LIMITS["iterations"] if self.free else 15
        if self.iterations >= limit:
            code = "FREE_ITERATION_BUDGET" if self.free else "ITERATION_BUDGET"
            raise BudgetExceeded(code, f"The run reached its {limit}-iteration limit.")
        self.iterations += 1

    def _check_time(self):
        if self.free and self.elapsed_seconds() >= FREE_LIMITS["wall_time_seconds"]:
            raise BudgetExceeded("FREE_TIME_BUDGET", "The free 90-second execution budget was exhausted.")

    def elapsed_seconds(self) -> float:
        return round(time.monotonic() - self.started, 3)

    def consumed(self, session=None) -> dict:
        usage = getattr(session, "usage", {}) if session else {}
        return {
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "iterations": self.iterations,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "elapsed_seconds": self.elapsed_seconds(),
        }


def classify_provider_failure(exc: Exception) -> tuple[str, str, bool, list[str], str | None]:
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    headers = getattr(response, "headers", {}) if response is not None else {}
    retry_after = headers.get("retry-after") if headers else None
    name = exc.__class__.__name__.lower()
    if status in (401, 403) or "authentication" in name or "permission" in name:
        return "INVALID_API_KEY", "The provider rejected this API key or its permissions.", False, [
            "Test or rotate the provider connection.", "Confirm the key can access the selected model."
        ], None
    if status == 429 or "ratelimit" in name:
        return "FREE_QUOTA_EXHAUSTED", "The provider's request or token quota was exhausted.", True, [
            "Retry after the provider quota resets.", "Reduce prompt size or split the task.", "Use a standard-tier key."
        ], retry_after
    if status == 404:
        return "MODEL_NOT_AVAILABLE", "The selected model is not available for this connection.", False, [
            "Refresh the model list and select an available model."
        ], None
    if status is not None and status >= 500:
        return "PROVIDER_UNAVAILABLE", "The model provider is temporarily unavailable.", True, [
            "Retry later without changing the prompt."
        ], retry_after
    if "timeout" in name:
        return "PROVIDER_TIMEOUT", "The provider did not respond before the timeout.", True, [
            "Retry later or reduce the task size."
        ], None
    return "PROVIDER_REQUEST_FAILED", "The provider could not complete the model request.", False, [
        "Test the provider connection.", "Verify model capabilities and reduce the request size."
    ], None


def failure_output(code: str, reason: str, consumed: dict, limits: dict, recommendations: list[str],
                   retryable: bool = False, retry_after: str | None = None,
                   partial_text: str = "", completed_tools: list[dict] | None = None) -> dict:
    partial = None
    if partial_text or completed_tools:
        partial = {"assistant_text": partial_text or None, "completed_tools": completed_tools or []}
    return {
        "error": reason,
        "failure": {
            "code": code,
            "reason": reason,
            "retryable": retryable,
            "retry_after": retry_after,
            "recommendations": recommendations,
            "consumed": consumed,
            "limits": limits,
        },
        "partial_output": partial,
    }
