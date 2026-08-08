import io
import unittest
from datetime import datetime, timezone

from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import ActivityEvent, ContentItem, IndexingJob, IngestionJob, WorkerHeartbeat
from app.modules.content.domain import IngestionFailure
from app.modules.content.parsers import DocumentParserFactory, PlainTextParser, detect_document_type
from app.modules.content.worker import IngestionWorker


class DocumentParserTest(unittest.TestCase):
    def test_text_is_utf8_normalized(self):
        parsed = PlainTextParser().parse("hello\r\nworld".encode())
        self.assertEqual("hello\nworld", parsed.text)
        self.assertEqual(11, parsed.character_count)

    def test_binary_text_is_rejected(self):
        with self.assertRaises(IngestionFailure) as caught:
            PlainTextParser().parse(b"hello\x00world")
        self.assertEqual("invalid_utf8", caught.exception.code)

    def test_detection_uses_pdf_signature_not_filename(self):
        self.assertEqual("application/pdf", detect_document_type("renamed.txt", b"%PDF-1.4\n"))

    def test_unsupported_extension_is_rejected(self):
        with self.assertRaises(IngestionFailure) as caught:
            detect_document_type("image.png", b"not an image")
        self.assertEqual("unsupported_type", caught.exception.code)

    def test_encrypted_pdf_is_rejected(self):
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
        writer.write(output)
        with self.assertRaises(IngestionFailure) as caught:
            DocumentParserFactory().create("application/pdf").parse(output.getvalue())
        self.assertEqual("encrypted_pdf", caught.exception.code)

    def test_textless_pdf_explains_ocr_is_deferred(self):
        output = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(output)
        with self.assertRaises(IngestionFailure) as caught:
            DocumentParserFactory().create("application/pdf").parse(output.getvalue())
        self.assertEqual("no_extractable_text", caught.exception.code)


class FakeStorage:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def download(self, _: str) -> bytes:
        return self.content


class IngestionWorkerTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        ContentItem.__table__.create(self.engine)
        IngestionJob.__table__.create(self.engine)
        IndexingJob.__table__.create(self.engine)
        ActivityEvent.__table__.create(self.engine)
        WorkerHeartbeat.__table__.create(self.engine)
        self.sessions = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def _queued_text(self) -> str:
        session = self.sessions()
        now = datetime.now(timezone.utc)
        item = ContentItem(id="document-1", user_id="tenant-1", agent_id=None,
                           knowledge_base_id="base-1", filename="notes.txt", storage_path="private/path",
                           extracted_text="", status="queued", mime_type="text/plain", size_bytes=5,
                           content_hash="hash", extraction_version=1, created_at=now, updated_at=now)
        session.add_all([item, IngestionJob(id="job-1", user_id="tenant-1", content_id=item.id,
                                           status="queued", available_at=now, created_at=now, updated_at=now)])
        session.commit()
        session.close()
        return "document-1"

    def test_worker_claims_and_completes_text_job(self):
        item_id = self._queued_text()
        self.assertTrue(IngestionWorker(self.sessions, FakeStorage(b"hello")).run_once())
        session = self.sessions()
        item = session.get(ContentItem, item_id)
        self.assertEqual("ready", item.status)
        self.assertEqual("hello", item.extracted_text)
        self.assertEqual("succeeded", session.query(IngestionJob).one().status)
        session.close()

    def test_deterministic_parser_failure_is_terminal(self):
        item_id = self._queued_text()
        IngestionWorker(self.sessions, FakeStorage(b"\x00binary")).run_once()
        session = self.sessions()
        item = session.get(ContentItem, item_id)
        self.assertEqual("failed", item.status)
        self.assertEqual("invalid_utf8", item.error_code)
        self.assertEqual("failed", session.query(IngestionJob).one().status)
        session.close()


if __name__ == "__main__":
    unittest.main()
