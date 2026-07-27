"""
searcher.py
-----------
Two-stage retrieval:
  1. FAISS bi-encoder retrieval  — fast, fetches top-K candidates (default 20)
  2. Cross-encoder reranking     — precise, keeps top-N (default 5)

Accepts a shared Embedder so the sentence-transformers model is only
loaded once per bot session, and an optional shared Reranker.
"""

import logging
from pathlib import Path

from storage  import Storage
from embedder import Embedder

logger = logging.getLogger(__name__)

# Stage-1: fetch more candidates than we'll return, to give the reranker options
FETCH_K    = 20
# Stage-2: keep this many after reranking
RETURN_K   = 5
# L2 distance ceiling — chunks beyond this are dropped before reranking
THRESHOLD  = 1.8


class Search:

    def __init__(self,
                 index_path:  str = "index.faiss",
                 chunks_path: str = "chunks.pkl",
                 embedder:    Embedder | None = None,
                 reranker=None,
                 threshold:   float = THRESHOLD):
        """
        embedder  — shared Embedder instance (or None → create own)
        reranker  — shared Reranker instance (or None → skip reranking)
        threshold — max L2 distance for stage-1 candidates
        """
        storage       = Storage()
        self.index    = storage.load_index(index_path)
        self.chunks   = self._normalize(storage.load_chunks(chunks_path))
        self.embedder = embedder or Embedder()
        self.reranker = reranker
        self.threshold = threshold

    # ── normalisation ─────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(chunks: list) -> list[dict]:
        out = []
        for c in chunks:
            if isinstance(c, dict) and "text" in c:
                out.append(c)
            else:
                out.append({"text": str(c), "source": ""})
        return out

    # ── query ─────────────────────────────────────────────────────────────────

    def query(self, question: str, top_k: int = RETURN_K) -> str:
        """
        Stage 1 — FAISS retrieval (fast, broad)
        Stage 2 — Cross-encoder reranking (precise, narrow)
        Returns joined text of the top chunks.
        """
        # ── Stage 1: FAISS ────────────────────────────────────────────────────
        vec = self.embedder.embedder.encode(
            [question], convert_to_numpy=True
        )
        fetch_k = max(FETCH_K, top_k * 4)
        distances, indices = self.index.search(vec, fetch_k)

        candidates = []
        for dist, i in zip(distances[0], indices[0]):
            if i == -1:
                continue
            if dist <= self.threshold:
                candidates.append(self.chunks[i]["text"])

        logger.debug(
            "FAISS: fetched %d candidates for %r (best L2=%.3f)",
            len(candidates), question,
            float(distances[0][0]) if len(distances[0]) else -1,
        )

        if not candidates:
            logger.warning(
                "RAG: 0 candidates passed threshold (best L2=%.3f, threshold=%.3f) for %r",
                float(distances[0][0]) if len(distances[0]) else -1,
                self.threshold, question,
            )
            return ""

        # ── Stage 2: reranking (if reranker available) ────────────────────────
        if self.reranker and len(candidates) > top_k:
            ranked = self.reranker.rerank(question, candidates, top_n=top_k)
        else:
            ranked = candidates[:top_k]

        return "\n\n".join(ranked)
