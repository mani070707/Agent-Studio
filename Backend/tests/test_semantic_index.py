import math
import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import ActivityEvent, ContentItem, DocumentChunk, IndexingJob, WorkerHeartbeat
from app.modules.semantic.chunking import DeterministicChunker
from app.modules.semantic.embedding import FastEmbedAdapter
from app.modules.semantic.domain import IndexFailure
from app.modules.semantic.worker import IndexingWorker


class WordCounter:
    def count_tokens(self, text: str) -> int:
        return len(text.split())


class SemanticChunkingTest(unittest.TestCase):
    def test_chunk_ids_and_boundaries_are_deterministic(self):
        text = "--- Page 1 ---\n" + " ".join(f"one-{i}" for i in range(12))
        text += "\n\n--- Page 2 ---\n" + " ".join(f"two-{i}" for i in range(12))
        chunker = DeterministicChunker(WordCounter(), target_tokens=10, max_tokens=12, overlap_tokens=2)
        first = chunker.chunk("doc-1", text, 1)
        second = chunker.chunk("doc-1", text, 1)
        self.assertEqual(first, second)
        self.assertTrue(all(chunk.token_count <= 12 for chunk in first))
        self.assertEqual(1, first[0].page_start)
        self.assertEqual(2, first[-1].page_end)

    def test_overlap_repeats_trailing_context(self):
        text = " ".join(f"word{i}" for i in range(25))
        chunks = DeterministicChunker(WordCounter(), target_tokens=10, max_tokens=12,
                                      overlap_tokens=2).chunk("doc", text, 1)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].text.split()[-2:], chunks[1].text.split()[:2])

    def test_empty_text_is_rejected(self):
        with self.assertRaises(IndexFailure) as caught:
            DeterministicChunker(WordCounter()).chunk("doc", "  ", 1)
        self.assertEqual("no_chunkable_text", caught.exception.code)

    def test_embedding_normalization_has_unit_length(self):
        normalized = FastEmbedAdapter._normalize([3.0, 4.0])
        self.assertAlmostEqual(1.0, math.sqrt(sum(value * value for value in normalized)))

    def test_embedding_model_cannot_silently_change(self):
        with self.assertRaises(IndexFailure) as caught:
            FastEmbedAdapter(model_name="different/model")
        self.assertEqual("unsupported_embedding_model", caught.exception.code)


class FakeEmbedder(WordCounter):
    model_name = "test-embedding"
    dimensions = 384

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 383 for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class IndexingWorkerTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        ContentItem.__table__.create(self.engine)
        IndexingJob.__table__.create(self.engine)
        DocumentChunk.__table__.create(self.engine)
        ActivityEvent.__table__.create(self.engine)
        WorkerHeartbeat.__table__.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def _queue(self):
        now = datetime.now(timezone.utc)
        session = self.sessions()
        session.add(ContentItem(id="doc", user_id="tenant", agent_id=None, knowledge_base_id="base",
                                filename="guide.txt", storage_path="private", extracted_text="use semantic search",
                                status="ready", mime_type="text/plain", extraction_version=1,
                                index_status="pending", created_at=now, updated_at=now))
        session.add(IndexingJob(id="index-job", user_id="tenant", content_id="doc", status="queued",
                                available_at=now, created_at=now, updated_at=now))
        session.commit()
        session.close()

    def test_worker_atomically_indexes_ready_document(self):
        self._queue()
        self.assertTrue(IndexingWorker(self.sessions, FakeEmbedder()).run_once())
        session = self.sessions()
        item = session.get(ContentItem, "doc")
        self.assertEqual("indexed", item.index_status)
        self.assertEqual(1, item.chunk_count)
        self.assertEqual("succeeded", session.get(IndexingJob, "index-job").status)
        self.assertEqual(1, session.query(DocumentChunk).count())
        session.close()

    def test_non_ready_document_fails_without_chunks(self):
        self._queue()
        session = self.sessions()
        session.get(ContentItem, "doc").status = "failed"
        session.commit()
        session.close()
        IndexingWorker(self.sessions, FakeEmbedder()).run_once()
        session = self.sessions()
        self.assertEqual("failed", session.get(ContentItem, "doc").index_status)
        self.assertEqual(0, session.query(DocumentChunk).count())
        session.close()


if __name__ == "__main__":
    unittest.main()
