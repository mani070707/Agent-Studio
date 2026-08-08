import hashlib
import re
import uuid
from dataclasses import dataclass

from app.modules.semantic.domain import ChunkDraft, IndexFailure
from app.modules.semantic.ports import TokenCounterPort

PAGE_PATTERN = re.compile(r"(?:^|\n\n)--- Page (\d+) ---\n")


@dataclass(frozen=True)
class _Unit:
    text: str
    page: int | None


class DeterministicChunker:
    def __init__(self, counter: TokenCounterPort, *, target_tokens: int = 384,
                 max_tokens: int = 480, overlap_tokens: int = 48) -> None:
        if not 0 <= overlap_tokens < target_tokens <= max_tokens <= 512:
            raise ValueError("Invalid chunking limits")
        self.counter = counter
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk(self, content_id: str, text: str, index_version: int) -> list[ChunkDraft]:
        units = self._units(text)
        if not units:
            raise IndexFailure("no_chunkable_text", "The extracted document contains no indexable text.")
        groups: list[list[_Unit]] = []
        current: list[_Unit] = []
        for unit in units:
            for bounded in self._split_oversized(unit):
                candidate = current + [bounded]
                if current and self.counter.count_tokens("\n\n".join(item.text for item in candidate)) > self.target_tokens:
                    groups.append(current)
                    current = self._overlap(current)
                if current and self.counter.count_tokens(
                    "\n\n".join(item.text for item in current + [bounded])
                ) > self.max_tokens:
                    current = []
                current.append(bounded)
                if self.counter.count_tokens("\n\n".join(item.text for item in current)) > self.max_tokens:
                    raise IndexFailure("chunk_limit_exceeded", "A text segment exceeds the model token limit.")
        if current:
            groups.append(current)

        drafts: list[ChunkDraft] = []
        for ordinal, group in enumerate(groups):
            chunk_text = "\n\n".join(unit.text for unit in group).strip()
            tokens = self.counter.count_tokens(chunk_text)
            if not chunk_text or tokens <= 0 or tokens > self.max_tokens:
                raise IndexFailure("chunk_limit_exceeded", "A generated chunk violates the token limits.")
            digest = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            pages = [unit.page for unit in group if unit.page is not None]
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{content_id}:{index_version}:{ordinal}:{digest}"))
            drafts.append(ChunkDraft(chunk_id, ordinal, chunk_text, tokens,
                                     min(pages) if pages else None, max(pages) if pages else None, digest))
        return drafts

    def _units(self, text: str) -> list[_Unit]:
        text = text.strip()
        if not text:
            return []
        matches = list(PAGE_PATTERN.finditer(text))
        pages: list[tuple[int | None, str]] = []
        if matches:
            for index, match in enumerate(matches):
                start = match.end()
                end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                pages.append((int(match.group(1)), text[start:end]))
        else:
            pages.append((None, text))
        units: list[_Unit] = []
        for page, body in pages:
            for paragraph in re.split(r"\n\s*\n", body):
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                if self.counter.count_tokens(paragraph) <= self.max_tokens:
                    units.append(_Unit(paragraph, page))
                else:
                    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
                    units.extend(_Unit(sentence.strip(), page) for sentence in sentences if sentence.strip())
        return units

    def _split_oversized(self, unit: _Unit) -> list[_Unit]:
        if self.counter.count_tokens(unit.text) <= self.max_tokens:
            return [unit]
        words = unit.text.split()
        pieces: list[_Unit] = []
        current: list[str] = []
        for word in words:
            if current and self.counter.count_tokens(" ".join(current + [word])) > self.target_tokens:
                pieces.append(_Unit(" ".join(current), unit.page))
                current = []
            current.append(word)
        if current:
            pieces.append(_Unit(" ".join(current), unit.page))
        return pieces

    def _overlap(self, units: list[_Unit]) -> list[_Unit]:
        overlap: list[_Unit] = []
        for unit in reversed(units):
            candidate = [unit] + overlap
            if self.counter.count_tokens("\n\n".join(item.text for item in candidate)) > self.overlap_tokens:
                if not overlap:
                    words = unit.text.split()
                    tail: list[str] = []
                    for word in reversed(words):
                        candidate_text = " ".join([word] + list(reversed(tail)))
                        if self.counter.count_tokens(candidate_text) > self.overlap_tokens:
                            break
                        tail.append(word)
                    if tail:
                        overlap = [_Unit(" ".join(reversed(tail)), unit.page)]
                break
            overlap = candidate
        return overlap
