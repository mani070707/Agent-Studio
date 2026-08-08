from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import Connection
from psycopg.rows import dict_row

from app.core.config import settings


def encrypted_serializer() -> EncryptedSerializer:
    key = settings.checkpoint_encryption_key.encode()
    if len(key) != 32:
        raise RuntimeError("CHECKPOINT_ENCRYPTION_KEY must contain exactly 32 characters")
    strict = JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=[])
    return EncryptedSerializer.from_pycryptodome_aes(strict, key=key)


@contextmanager
def checkpoint_context():
    # PostgresSaver.from_conn_string does not currently expose its serializer argument,
    # so construct the official saver with the same connection settings explicitly.
    with Connection.connect(settings.database_url, autocommit=True, prepare_threshold=0,
                            row_factory=dict_row) as connection:
        yield PostgresSaver(connection, serde=encrypted_serializer())


def setup_checkpoints() -> None:
    with checkpoint_context() as saver:
        saver.setup()


def delete_checkpoint_thread(thread_id: str) -> None:
    with checkpoint_context() as saver:
        saver.delete_thread(thread_id)
