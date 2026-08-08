from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, PrivateAttr

from app.modules.retrieval.service import EvidenceLedger


class AgentStudioLangChainRetriever(BaseRetriever):
    """LangChain view over our tenant-safe hybrid retriever; it never owns authorization or storage."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    retriever: Any
    version_id: str
    user_id: str
    ledger: Any
    top_k: int = 6
    max_per_document: int = 3
    token_budget: int = 2500
    _last_evidence: list = PrivateAttr(default_factory=list)
    _last_stats: dict = PrivateAttr(default_factory=dict)

    def _get_relevant_documents(self, query: str, *, run_manager=None) -> list[Document]:
        evidence, stats = self.retriever.retrieve(
            self.version_id, self.user_id, query, top_k=self.top_k,
            max_per_document=self.max_per_document, token_budget=self.token_budget, ledger=self.ledger)
        self._last_evidence, self._last_stats = evidence, stats
        return [Document(page_content=item.excerpt, metadata=item.citation()) for item in evidence]

    @property
    def last_evidence(self) -> list:
        return self._last_evidence

    @property
    def last_stats(self) -> dict:
        return self._last_stats
