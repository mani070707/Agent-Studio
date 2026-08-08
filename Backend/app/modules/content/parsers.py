import unicodedata

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.modules.content.domain import IngestionFailure, ParsedDocument
from app.modules.content.ports import DocumentParser

MAX_PDF_PAGES = 250
MAX_EXTRACTED_CHARS = 500_000


class PlainTextParser:
    def parse(self, content: bytes) -> ParsedDocument:
        if b"\x00" in content:
            raise IngestionFailure("invalid_utf8", "The file contains binary data and is not valid text.")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IngestionFailure("invalid_utf8", "Text and Markdown files must use UTF-8 encoding.") from exc
        text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
        if len(text) > MAX_EXTRACTED_CHARS:
            raise IngestionFailure("file_too_large", "Extracted text exceeds 500,000 characters.")
        if not text.strip():
            raise IngestionFailure("no_extractable_text", "The document contains no meaningful text.")
        return ParsedDocument(text=text, page_count=None, character_count=len(text))


class PdfDocumentParser:
    def parse(self, content: bytes) -> ParsedDocument:
        import io

        try:
            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise IngestionFailure("encrypted_pdf", "Password-protected PDFs are not supported.")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise IngestionFailure("page_limit_exceeded", "PDFs may contain at most 250 pages.")
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
        except IngestionFailure:
            raise
        except (PdfReadError, ValueError, OSError) as exc:
            raise IngestionFailure("corrupt_pdf", "The PDF is corrupt or cannot be read.") from exc
        text = "\n\n".join(f"--- Page {index} ---\n{page}" for index, page in enumerate(pages, 1))
        if not any(page for page in pages):
            raise IngestionFailure("no_extractable_text", "No text was found. Scanned PDFs require OCR, which is not available yet.")
        if len(text) > MAX_EXTRACTED_CHARS:
            raise IngestionFailure("file_too_large", "Extracted text exceeds 500,000 characters.")
        return ParsedDocument(text=text, page_count=len(pages), character_count=len(text))


class DocumentParserFactory:
    def __init__(self) -> None:
        text_parser = PlainTextParser()
        self._parsers: dict[str, DocumentParser] = {
            "application/pdf": PdfDocumentParser(),
            "text/plain": text_parser,
            "text/markdown": text_parser,
        }

    def create(self, mime_type: str) -> DocumentParser:
        parser = self._parsers.get(mime_type)
        if not parser:
            raise IngestionFailure("unsupported_type", "Only PDF, TXT and Markdown files are supported.")
        return parser


def detect_document_type(filename: str, content: bytes) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in {"txt", "md", "markdown"}:
        raise IngestionFailure("unsupported_type", "Only PDF, TXT and Markdown files are supported.")
    if b"\x00" in content:
        raise IngestionFailure("invalid_utf8", "The file contains binary data and is not valid text.")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IngestionFailure("invalid_utf8", "Text and Markdown files must use UTF-8 encoding.") from exc
    return "text/markdown" if suffix in {"md", "markdown"} else "text/plain"
