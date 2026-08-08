from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    id: str
    name: str
    tool_calling: bool
    structured_output: bool
    context_window: int
    free_max_output_tokens: int = 2048


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    id: str
    name: str
    free_tier_available: bool
    notice: str
    models: tuple[ModelDefinition, ...]


class ProviderCatalog:
    """Versioned, code-owned provider capabilities; no database seeding required."""

    def __init__(self) -> None:
        model = lambda identifier, context: ModelDefinition(identifier, identifier, True, True, context)
        self._providers = {
            "gemini": ProviderDefinition("gemini", "Google Gemini", True,
                "Free tier is for learning and limited workloads; review Google's data-use policy.",
                (model("gemini-3.6-flash", 1_000_000), model("gemini-2.5-flash", 1_000_000),
                 model("gemini-2.5-flash-lite", 1_000_000))),
            "groq": ProviderDefinition("groq", "Groq", True,
                "Free limits vary by model and organization and can reset at different intervals.",
                (model("llama-3.1-8b-instant", 131_072), model("llama-3.3-70b-versatile", 131_072),
                 model("openai/gpt-oss-20b", 131_072))),
            "openrouter": ProviderDefinition("openrouter", "OpenRouter Free", True,
                "Free models have low quotas and availability can change without notice.",
                (model("openrouter/free", 128_000),)),
            "openai": ProviderDefinition("openai", "OpenAI", False,
                "Billing or promotional credits may be required.", (model("gpt-4o-mini", 128_000),)),
            "anthropic": ProviderDefinition("anthropic", "Anthropic", False,
                "Billing or promotional credits may be required.", (model("claude-sonnet-5", 200_000),)),
        }

    def all(self) -> list[ProviderDefinition]:
        return sorted(self._providers.values(), key=lambda item: item.name)

    def require(self, provider: str) -> ProviderDefinition:
        try:
            return self._providers[provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported provider: {provider}") from exc
