from app.llm.anthropic_session import AnthropicSession
from app.llm.openai_session import OpenAISession
from app.llm.gemini_session import GeminiSession

_SESSION_CLASSES = {"anthropic": AnthropicSession, "openai": OpenAISession, "gemini": GeminiSession}


def create_session(provider: str, **kwargs):
    if provider == "groq":
        return OpenAISession(provider=provider, base_url="https://api.groq.com/openai/v1", **kwargs)
    if provider == "openrouter":
        return OpenAISession(
            provider=provider,
            base_url="https://openrouter.ai/api/v1",
            default_headers={"HTTP-Referer": "https://agent-studio.local", "X-Title": "Agent Studio"},
            **kwargs,
        )
    if provider not in _SESSION_CLASSES:
        raise ValueError(f"Unsupported LLM provider: {provider}. Supported: {list(_SESSION_CLASSES)}")
    return _SESSION_CLASSES[provider](**kwargs)
