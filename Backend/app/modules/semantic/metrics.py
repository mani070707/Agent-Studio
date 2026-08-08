import threading
from collections import Counter


class SemanticMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.indexed_documents = 0
        self.chunks_generated = 0
        self.indexing_duration_seconds = 0.0
        self.searches = 0
        self.search_duration_seconds = 0.0
        self.failures: Counter[str] = Counter()
        self.retrieval_semantic_candidates = 0
        self.retrieval_keyword_candidates = 0
        self.retrieval_fused_results = 0
        self.retrieval_context_tokens = 0
        self.empty_retrievals = 0
        self.invalid_citations = 0

    def record_index(self, chunks: int, duration: float) -> None:
        with self._lock:
            self.indexed_documents += 1
            self.chunks_generated += chunks
            self.indexing_duration_seconds += duration

    def record_failure(self, code: str) -> None:
        with self._lock:
            self.failures[code] += 1

    def record_search(self, duration: float) -> None:
        with self._lock:
            self.searches += 1
            self.search_duration_seconds += duration

    def record_retrieval(self, stats: dict) -> None:
        with self._lock:
            self.retrieval_semantic_candidates += int(stats.get("semantic_candidates", 0))
            self.retrieval_keyword_candidates += int(stats.get("keyword_candidates", 0))
            self.retrieval_fused_results += int(stats.get("fused_results", 0))
            self.retrieval_context_tokens += int(stats.get("context_tokens", 0))
            if not stats.get("fused_results"):
                self.empty_retrievals += 1

    def record_invalid_citation(self) -> None:
        with self._lock:
            self.invalid_citations += 1

    def prometheus_lines(self) -> list[str]:
        with self._lock:
            lines = [
                f"agent_studio_indexed_document_total {self.indexed_documents}",
                f"agent_studio_indexed_chunk_total {self.chunks_generated}",
                f"agent_studio_indexing_duration_seconds_total {self.indexing_duration_seconds:.6f}",
                f"agent_studio_semantic_search_total {self.searches}",
                f"agent_studio_semantic_search_duration_seconds_total {self.search_duration_seconds:.6f}",
                f"agent_studio_retrieval_semantic_candidate_total {self.retrieval_semantic_candidates}",
                f"agent_studio_retrieval_keyword_candidate_total {self.retrieval_keyword_candidates}",
                f"agent_studio_retrieval_fused_result_total {self.retrieval_fused_results}",
                f"agent_studio_retrieval_context_token_total {self.retrieval_context_tokens}",
                f"agent_studio_retrieval_empty_total {self.empty_retrievals}",
                f"agent_studio_invalid_citation_total {self.invalid_citations}",
            ]
            lines.extend(f'agent_studio_indexing_failure_total{{code="{code}"}} {count}'
                         for code, count in sorted(self.failures.items()))
            return lines


semantic_metrics = SemanticMetrics()
