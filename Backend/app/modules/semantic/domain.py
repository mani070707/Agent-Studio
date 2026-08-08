from dataclasses import dataclass


class IndexFailure(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class ChunkDraft:
    id: str
    ordinal: int
    text: str
    token_count: int
    page_start: int | None
    page_end: int | None
    text_hash: str


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    content_id: str
    filename: str
    ordinal: int
    page_start: int | None
    page_end: int | None
    score: float
    excerpt: str
