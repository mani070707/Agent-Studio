from app.storage.supabase_storage import delete_file, download_file, upload_file


class SupabaseObjectStorage:
    def upload(self, path: str, content: bytes, content_type: str) -> None:
        upload_file(path, content, content_type)

    def download(self, path: str) -> bytes:
        return download_file(path)

    def delete(self, path: str) -> None:
        delete_file(path)
