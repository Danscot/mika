import logging
import numpy as np
from storage import Storage
from embedder import Embedder

logger = logging.getLogger(__name__)


class Search:
    """
    RAG Search class using FAISS + embedded chunks.

    Uses L2 (Euclidean) distance — LOWER distance means MORE similar.
    Threshold guide for all-MiniLM-L6-v2:
      • Very similar:   ~0.0 – 0.5
      • Related:        ~0.5 – 1.8
      • Unrelated:      > 1.8

    Chunks can be stored as plain strings (legacy) or dicts {"text":..., "source":...}.
    Both formats are handled transparently.
    """

    def __init__(self, index_path="index.faiss", chunks_path="chunks.pkl", threshold=1.8):
        self.storage   = Storage()
        self.index     = self.storage.load_index(index_path)
        self.chunks    = self._normalize_chunks(self.storage.load_chunks(chunks_path))
        self.embedder  = Embedder()
        self.threshold = threshold

    # ── internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _normalize_chunks(chunks: list) -> list[dict]:
        """
        Normalize any mix of bare strings and dicts into uniform dicts.
        This handles indexes built before the dict-chunk migration.
        """
        normalized = []
        for c in chunks:
            if isinstance(c, dict) and "text" in c:
                normalized.append(c)
            else:
                normalized.append({"text": str(c), "source": ""})
        return normalized

    # ── public API ────────────────────────────────────────────────────────────

    def query(self, question: str, top_k: int = 5) -> str:
        """
        Search the FAISS index for the top_k most relevant chunks.
        Returns a joined string of sufficiently similar chunks,
        or an empty string when nothing passes the threshold.
        """
        query_vec = self.embedder.embedder.encode(
            [question], convert_to_numpy=True
        )

        distances, indices = self.index.search(query_vec, top_k)

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
            best = float(distances[0][0]) if len(distances[0]) else -1
            logger.warning(
                "RAG: 0 chunks matched for %r  "
                "(best L2=%.3f, threshold=%.3f). "
                "Tip: raise threshold or re-ingest.",
                question, best, self.threshold,
            )

        return "\n\n".join(results)
