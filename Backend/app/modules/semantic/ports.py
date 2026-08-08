from typing import Protocol

from app.modules.semantic.domain import ChunkDraft


class TokenCounterPort(Protocol):
    def count_tokens(self, text: str) -> int: ...


class ChunkerPort(Protocol):
    def chunk(self, content_id: str, text: str, index_version: int) -> list[ChunkDraft]: ...


class EmbeddingPort(TokenCounterPort, Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
