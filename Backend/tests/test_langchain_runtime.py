import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.routers.agents import HarnessConfig
from app.runtime.direct import DirectRuntimeSession
from app.runtime.langchain import LangChainRuntimeSession, RuntimeTimingCallback, _model
from app.runtime.retriever import AgentStudioLangChainRetriever


class FakeDirectSession:
    provider = "openai"

    def __init__(self):
        self.usage = {"model_calls": 1, "input_tokens": 4, "output_tokens": 2}

    def send(self, message):
        return {"text": "", "tool_calls": [{"id": "1", "name": "final_answer", "arguments": {}}]}

    def send_tool_results(self, results):
        return {"text": "ok", "tool_calls": []}


class RuntimeContractTest(unittest.TestCase):
    def test_direct_adapter_normalizes_stats(self):
        session = DirectRuntimeSession(FakeDirectSession())
        self.assertEqual(session.send("hello")["tool_calls"][0]["name"], "final_answer")
        self.assertEqual(session.stats()["input_tokens"], 4)
        self.assertIn("provider_latency_ms", session.stats())

    def test_langchain_text_redacts_non_text_blocks(self):
        content = [{"type": "thinking", "text": "private"}, {"type": "text", "text": "answer"}]
        self.assertEqual(LangChainRuntimeSession._safe_text(content), "answer")

    def test_callback_retains_no_prompts_or_responses(self):
        callback = RuntimeTimingCallback()
        callback.on_chat_model_start({}, [["secret prompt"]], run_id="one")
        callback.on_llm_end(None, run_id="one")
        self.assertFalse(hasattr(callback, "prompts"))
        self.assertGreaterEqual(callback.provider_latency_ms, 0)

    def test_lcel_turn_normalizes_tool_calls_and_usage(self):
        session = object.__new__(LangChainRuntimeSession)
        session.provider = "openai"
        session.usage = {"model_calls": 0, "input_tokens": 0, "output_tokens": 0}
        session.callback = RuntimeTimingCallback()
        session.messages = []
        session._overhead_ms = 0
        session.chain = RunnableLambda(lambda _: AIMessage(
            content="", tool_calls=[{"id": "call-1", "name": "final_answer", "args": {"ok": True}}],
            usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7}))
        turn = session.send("hello")
        self.assertEqual(turn["tool_calls"], [{"id": "call-1", "name": "final_answer", "arguments": {"ok": True}}])
        self.assertEqual(session.stats()["input_tokens"], 5)

    def test_legacy_harness_defaults_to_direct(self):
        harness = HarnessConfig.model_validate({"runtime_model": {"provider": "openai", "model_id": "model"}})
        self.assertEqual(harness.runtime_engine, "direct")


class ProviderFactoryTest(unittest.TestCase):
    @patch("app.runtime.langchain.ChatGoogleGenerativeAI")
    @patch("app.runtime.langchain.ChatAnthropic")
    @patch("app.runtime.langchain.ChatOpenAI")
    def test_all_provider_mappings(self, openai, anthropic, google):
        kwargs = {"api_key": "secret", "model": "model", "temperature": 0, "max_tokens": 10, "timeout": 2}
        for provider in ("openai", "groq", "openrouter"):
            _model(provider, **kwargs)
        self.assertEqual(openai.call_count, 3)
        self.assertEqual(openai.call_args_list[1].kwargs["base_url"], "https://api.groq.com/openai/v1")
        self.assertEqual(openai.call_args_list[2].kwargs["base_url"], "https://openrouter.ai/api/v1")
        _model("anthropic", **kwargs)
        _model("gemini", **kwargs)
        anthropic.assert_called_once()
        google.assert_called_once()


class LangChainRetrieverTest(unittest.TestCase):
    def test_documents_keep_trusted_evidence_metadata(self):
        evidence = SimpleNamespace(excerpt="policy text", citation=lambda: {
            "source_id": "S1", "document_id": "doc", "chunk_id": "chunk", "score": .9})
        hybrid = SimpleNamespace(retrieve=lambda *args, **kwargs: ([evidence], {"fused_results": 1}))
        adapter = AgentStudioLangChainRetriever(
            retriever=hybrid, version_id="v", user_id="u", ledger=object())
        documents = adapter.invoke("policy")
        self.assertEqual(documents[0].page_content, "policy text")
        self.assertEqual(documents[0].metadata["source_id"], "S1")
        self.assertEqual(adapter.last_stats["fused_results"], 1)


if __name__ == "__main__":
    unittest.main()
