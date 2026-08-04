from app.llm.anthropic_session import AnthropicSession
from app.llm.openai_session import OpenAISession

_SESSION_CLASSES = {"anthropic": AnthropicSession, "openai": OpenAISession}


def create_session(provider: str, **kwargs):
    if provider not in _SESSION_CLASSES:
        raise ValueError(f"Unsupported LLM provider: {provider}. Supported: {list(_SESSION_CLASSES)}")
    return _SESSION_CLASSES[provider](**kwargs)
