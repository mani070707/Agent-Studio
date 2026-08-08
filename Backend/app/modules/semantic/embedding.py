import math
import threading

from fastembed import TextEmbedding

from app.modules.semantic.domain import IndexFailure


class FastEmbedAdapter:
    model_name = "BAAI/bge-small-en-v1.5"
    dimensions = 384

    def __init__(self, *, model_name: str = model_name, cache_dir: str | None = None, batch_size: int = 32) -> None:
        if model_name != self.model_name:
            raise IndexFailure("unsupported_embedding_model",
                               f"This index version requires {self.model_name}.")
        self.cache_dir = cache_dir
        self.batch_size = batch_size
        self._model: TextEmbedding | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> TextEmbedding:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
                    except Exception as exc:
                        raise IndexFailure("embedding_model_unavailable",
                                           "The local embedding model is unavailable.", retryable=True) from exc
        return self._model

    def count_tokens(self, text: str) -> int:
        try:
            return int(self.model.token_count(text))
        except IndexFailure:
            raise
        except Exception as exc:
            raise IndexFailure("embedding_model_unavailable",
                               "The local embedding tokenizer is unavailable.", retryable=True) from exc

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        try:
            vectors = [self._normalize(vector.tolist()) for vector in self.model.embed(texts, batch_size=self.batch_size)]
        except IndexFailure:
            raise
        except Exception as exc:
            raise IndexFailure("embedding_model_unavailable",
                               "The local embedding model could not process this text.", retryable=True) from exc
        if len(vectors) != len(texts) or any(len(vector) != self.dimensions for vector in vectors):
            raise IndexFailure("invalid_embedding", "The embedding model returned an invalid vector.")
        return vectors

    @staticmethod
    def _normalize(vector: list[float]) -> list[float]:
        magnitude = math.sqrt(sum(value * value for value in vector))
        if not magnitude:
            raise IndexFailure("invalid_embedding", "The embedding model returned an empty vector.")
        return [value / magnitude for value in vector]
