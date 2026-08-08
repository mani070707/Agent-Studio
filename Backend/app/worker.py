import signal
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.content.storage import SupabaseObjectStorage
from app.modules.content.worker import IngestionWorker
from app.modules.semantic.embedding import FastEmbedAdapter
from app.modules.semantic.worker import IndexingWorker
from app.workflows.worker import WorkflowWorker
from app.workflows.checkpoints import setup_checkpoints


def main() -> None:
    if len(settings.checkpoint_encryption_key) != 32:
        raise RuntimeError("CHECKPOINT_ENCRYPTION_KEY must contain exactly 32 characters")
    setup_checkpoints()
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    worker = IngestionWorker(SessionLocal, SupabaseObjectStorage(), lease_seconds=settings.ingestion_lease_seconds)
    index_worker = IndexingWorker(
        SessionLocal,
        FastEmbedAdapter(model_name=settings.embedding_model, cache_dir=settings.embedding_cache_dir,
                         batch_size=settings.embedding_batch_size),
        index_version=settings.semantic_index_version,
        lease_seconds=settings.indexing_lease_seconds,
        timeout_seconds=settings.indexing_timeout_seconds,
    )
    workflow_worker = WorkflowWorker(SessionLocal, lease_seconds=settings.workflow_lease_seconds)
    while not stopping:
        if not worker.run_once() and not index_worker.run_once() and not workflow_worker.run_once():
            time.sleep(settings.ingestion_poll_seconds)


if __name__ == "__main__":
    main()
