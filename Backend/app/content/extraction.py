import io

from pypdf import PdfReader

MAX_CHARS = 500_000


def extract_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif lower.endswith((".txt", ".md", ".csv", ".json")):
        text = content.decode("utf-8", errors="replace")
    else:
        text = ""
    return text[:MAX_CHARS]
