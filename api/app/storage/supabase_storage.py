from supabase import Client, create_client

from app.core.config import settings

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client


def upload_file(storage_path: str, content: bytes, content_type: str = "application/octet-stream") -> None:
    client = _get_client()
    client.storage.from_(settings.supabase_storage_bucket).upload(
        storage_path, content, file_options={"content-type": content_type, "upsert": "true"}
    )


def delete_file(storage_path: str) -> None:
    client = _get_client()
    client.storage.from_(settings.supabase_storage_bucket).remove([storage_path])
