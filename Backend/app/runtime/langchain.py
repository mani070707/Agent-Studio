import os
from time import monotonic
from typing import Any

# Privacy is an application invariant: framework traces stay inside Agent Studio.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI


class RuntimeTimingCallback(BaseCallbackHandler):
    """Collects timings only. Prompts and responses are deliberately never retained."""

    def __init__(self) -> None:
        self._starts: dict[str, float] = {}
        self.provider_latency_ms = 0.0

    def on_llm_start(self, serialized, prompts, *, run_id, **kwargs) -> None:
        self._starts[str(run_id)] = monotonic()

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs) -> None:
        self._starts[str(run_id)] = monotonic()

    def on_llm_end(self, response, *, run_id, **kwargs) -> None:
        started = self._starts.pop(str(run_id), None)
        if started is not None:
            self.provider_latency_ms += (monotonic() - started) * 1000

    def on_llm_error(self, error, *, run_id, **kwargs) -> None:
        self.on_llm_end(None, run_id=run_id)


def _model(provider: str, *, api_key: str, model: str, temperature: float,
           max_tokens: int, timeout: float):
    common = {"temperature": temperature, "max_retries": 0}
    if provider in {"openai", "groq", "openrouter"}:
        options: dict[str, Any] = {**common, "api_key": api_key, "model": model,
                                   "max_completion_tokens": max_tokens, "timeout": timeout}
        if provider == "groq":
            options["base_url"] = "https://api.groq.com/openai/v1"
        elif provider == "openrouter":
            options["base_url"] = "https://openrouter.ai/api/v1"
            options["default_headers"] = {"HTTP-Referer": "https://agent-studio.local", "X-Title": "Agent Studio"}
        return ChatOpenAI(**options)
    if provider == "anthropic":
        return ChatAnthropic(api_key=api_key, model_name=model, max_tokens_to_sample=max_tokens,
                             temperature=temperature, timeout=timeout, max_retries=0)
    if provider == "gemini":
        return ChatGoogleGenerativeAI(api_key=api_key, model=model, max_tokens=max_tokens,
                                      temperature=temperature, request_timeout=timeout, retries=0)
    raise ValueError(f"Unsupported LangChain provider: {provider}")


class LangChainRuntimeSession:
    def __init__(self, *, provider: str, api_key: str, model: str, temperature: float,
                 max_tokens: int, system_prompt: str, tools: list[dict], timeout: float = 300.0) -> None:
        self.provider = provider
        self.usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.callback = RuntimeTimingCallback()
        schemas = [{"type": "function", "function": {"name": item["name"],
                    "description": item["description"], "parameters": item["input_schema"]}} for item in tools]
        chat_model = _model(provider, api_key=api_key, model=model, temperature=temperature,
                            max_tokens=max_tokens, timeout=timeout).bind_tools(schemas)
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt), MessagesPlaceholder(variable_name="messages"),
        ])
        self.chain = prompt | chat_model
        self.messages = []
        self._overhead_ms = 0.0

    def _invoke(self) -> dict:
        started = monotonic()
        response: AIMessage = self.chain.invoke(
            {"messages": self.messages}, config={"callbacks": [self.callback], "tags": ["agent-studio"]})
        invoked = monotonic()
        self.messages.append(response)
        usage = response.usage_metadata or {}
        self.usage["model_calls"] += 1
        self.usage["input_tokens"] += int(usage.get("input_tokens", 0))
        self.usage["output_tokens"] += int(usage.get("output_tokens", 0))
        tool_calls = [{"id": call.get("id") or "", "name": call["name"],
                       "arguments": call.get("args") or {}} for call in response.tool_calls]
        text = self._safe_text(response.content)
        self._overhead_ms += max(0.0, (monotonic() - invoked) * 1000)
        return {"tool_calls": tool_calls, "text": text}

    @staticmethod
    def _safe_text(content) -> str:
        if isinstance(content, str):
            return content
        return "".join(str(block.get("text", "")) for block in content
                       if isinstance(block, dict) and block.get("type") in {"text", "output_text"})

    def send(self, user_message: str) -> dict:
        self.messages.append(HumanMessage(content=user_message))
        return self._invoke()

    def send_tool_results(self, results: list[dict]) -> dict:
        for result in results:
            self.messages.append(ToolMessage(content=str(result["output"]),
                                             tool_call_id=result["id"], name=result["name"]))
        return self._invoke()

    def stats(self) -> dict:
        return {**self.usage, "provider_latency_ms": round(self.callback.provider_latency_ms, 2),
                "orchestration_overhead_ms": round(self._overhead_ms, 2)}
