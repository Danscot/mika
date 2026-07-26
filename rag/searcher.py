"""
searcher.py
-----------
FAISS similarity search over ingested chunks.

Accepts an optional shared Embedder instance so the sentence-transformers
model is only loaded once per bot session, not once per index.
"""

import logging
from pathlib import Path

from storage import Storage
from embedder import Embedder

logger = logging.getLogger(__name__)


class Search:

    def __init__(self, index_path: str = "index.faiss",
                 chunks_path: str = "chunks.pkl",
                 embedder: Embedder | None = None,
                 threshold: float = 1.8):
        """
        embedder  – pass a shared Embedder to avoid loading the model twice.
                    If None, a new Embedder is created (standalone usage).
        threshold – maximum L2 distance to accept a chunk as relevant.
                    For all-MiniLM-L6-v2: ~0-0.5 very similar, ~0.5-1.8 related.
        """
        storage          = Storage()
        self.index       = storage.load_index(index_path)
        self.chunks      = self._normalize(storage.load_chunks(chunks_path))
        self.embedder    = embedder or Embedder()
        self.threshold   = threshold

    # ── Normalisation ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(chunks: list) -> list[dict]:
        """Coerce old bare-string chunks to {"text": ..., "source": ""} dicts."""
        out = []
        for c in chunks:
            if isinstance(c, dict) and "text" in c:
                out.append(c)
            else:
                out.append({"text": str(c), "source": ""})
        return out

    # ── Query ─────────────────────────────────────────────────────────────────

    def query(self, question: str, top_k: int = 5) -> str:
        """
        Embed the question, search FAISS, return joined chunk texts.
        Returns an empty string if nothing passes the threshold.
        """
        vec = self.embedder.embedder.encode(
            [question], convert_to_numpy=True
        )
        distances, indices = self.index.search(vec, top_k)

        logger.debug(
            "RAG distances for %r: %s",
            question,
            [(round(float(d), 3), int(i)) for d, i in zip(distances[0], indices[0])],
        )

        results = []
        for dist, i in zip(distances[0], indices[0]):
            if i == -1:
                continue
            if dist <= self.threshold:
                results.append(self.chunks[i]["text"])

        if not results:
            logger.warning(
                "RAG: 0 chunks matched for %r (best L2=%.3f, threshold=%.3f)",
                question,
                float(distances[0][0]) if len(distances[0]) else -1,
                self.threshold,
            )

        return "\n\n".join(results)
