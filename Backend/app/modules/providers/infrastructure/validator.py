import httpx


class ProviderValidationError(ValueError):
    def __init__(self, message: str, *, rate_limited: bool = False) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited


class ProviderKeyValidator:
    """Strategy adapter for quota-free provider model-list/key endpoints."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=10.0)

    def available_models(self, provider: str, api_key: str) -> set[str]:
        try:
            if provider == "gemini":
                response = self.client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                           params={"key": api_key})
            elif provider == "anthropic":
                response = self.client.get("https://api.anthropic.com/v1/models",
                                           headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})
            elif provider == "openrouter":
                auth = {"Authorization": f"Bearer {api_key}"}
                self._raise_for_provider(self.client.get("https://openrouter.ai/api/v1/auth/key", headers=auth))
                response = self.client.get("https://openrouter.ai/api/v1/models", headers=auth)
            else:
                base = {"groq": "https://api.groq.com/openai/v1/models",
                        "openai": "https://api.openai.com/v1/models"}.get(provider)
                if not base:
                    raise ProviderValidationError(f"Unsupported provider: {provider}")
                response = self.client.get(base, headers={"Authorization": f"Bearer {api_key}"})
            self._raise_for_provider(response)
            payload = response.json()
            rows = payload.get("models", []) if provider == "gemini" else payload.get("data", [])
            identifiers = set()
            for row in rows:
                identifier = row.get("id") or row.get("name", "")
                identifiers.add(identifier.removeprefix("models/"))
            return identifiers
        except ProviderValidationError:
            raise
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderValidationError("Provider validation is temporarily unavailable") from exc

    @staticmethod
    def _raise_for_provider(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise ProviderValidationError("Provider rate limit reached while validating the key", rate_limited=True)
        if response.status_code >= 400:
            raise ProviderValidationError("Provider rejected the API key")
