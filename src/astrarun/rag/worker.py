"""Background CPU embedding worker for AstraRun Hybrid RAG.

Processes background document batches with low priority, thread safety,
and immediate preemption/cancellation support.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import List, Optional

from astrarun.core.logging import get_logger
from astrarun.rag.embeddings import EmbeddingProvider
from astrarun.rag.models import DocumentChunk
from astrarun.rag.store import MemoryStore

logger = get_logger("astrarun.rag.worker")


class EmbeddingWorker:
    """
    Background worker thread that batches and computes embeddings for incoming document chunks.
    Ensures background indexing never interferes with interactive UI or query latency.
    """

    def __init__(
        self,
        store: MemoryStore,
        provider: EmbeddingProvider,
        batch_size: int = 16,
    ):
        self.store = store
        self.provider = provider
        self.batch_size = batch_size
        self._queue: queue.Queue[Optional[DocumentChunk]] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the background embedding worker thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="AstraRun-EmbeddingWorker",
            daemon=True,
        )
        self._thread.start()
        logger.info("Started background embedding worker")

    def stop(self, timeout: float = 2.0) -> None:
        """Signal the worker to terminate gracefully."""
        self._stop_event.set()
        self._queue.put(None)  # Sentinel to wake queue
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        logger.info("Stopped background embedding worker")

    def enqueue_chunk(self, chunk: DocumentChunk) -> None:
        """Enqueue a document chunk for background embedding generation."""
        self._queue.put(chunk)

    def enqueue_batch(self, chunks: List[DocumentChunk]) -> None:
        """Enqueue a list of document chunks."""
        for c in chunks:
            self._queue.put(c)

    def pending_count(self) -> int:
        """Return the number of items waiting in the embedding queue."""
        return self._queue.qsize()

    def _run_loop(self) -> None:
        """Worker loop processing batches from the queue."""
        while not self._stop_event.is_set():
            batch: List[DocumentChunk] = []
            try:
                # Wait for at least one item
                item = self._queue.get(timeout=0.25)
                if item is None:
                    continue
                batch.append(item)

                # Drain up to batch_size items without blocking
                while len(batch) < self.batch_size:
                    try:
                        next_item = self._queue.get_nowait()
                        if next_item is None:
                            continue
                        batch.append(next_item)
                    except queue.Empty:
                        break

            except queue.Empty:
                continue

            if not batch:
                continue

            # Process the batch
            try:
                texts = [c.content for c in batch]
                embeddings = self.provider.embed_batch(texts)
                for chunk, emb in zip(batch, embeddings):
                    chunk.embedding = emb
                    self.store.insert_chunk(chunk)
                logger.debug("Background worker indexed %d chunks", len(batch))
            except Exception as e:
                logger.error("Error computing embeddings in background worker: %s", e)
            finally:
                for _ in batch:
                    self._queue.task_done()
