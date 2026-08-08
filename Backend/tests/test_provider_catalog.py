import unittest

import httpx

from app.modules.providers.domain import ProviderCatalog
from app.modules.providers.infrastructure.validator import ProviderKeyValidator, ProviderValidationError


class ProviderCatalogTest(unittest.TestCase):
    def test_catalog_contains_all_supported_providers(self):
        self.assertEqual(
            {"gemini", "groq", "openrouter", "openai", "anthropic"},
            {provider.id for provider in ProviderCatalog().all()},
        )

    def test_groq_models_are_parsed_without_exposing_key(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual("Bearer test-secret", request.headers["authorization"])
            return httpx.Response(200, json={"data": [{"id": "llama-3.1-8b-instant"}]})

        validator = ProviderKeyValidator(httpx.Client(transport=httpx.MockTransport(handler)))
        self.assertEqual({"llama-3.1-8b-instant"}, validator.available_models("groq", "test-secret"))

    def test_rate_limit_is_classified(self):
        validator = ProviderKeyValidator(httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(429, json={"secret": "must-not-leak"}))
        ))
        with self.assertRaises(ProviderValidationError) as caught:
            validator.available_models("openai", "test-secret")
        self.assertTrue(caught.exception.rate_limited)
        self.assertNotIn("must-not-leak", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
