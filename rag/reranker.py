"""
reranker.py
-----------
Cross-encoder reranking on top of FAISS retrieval.

WHY RERANK:
  FAISS retrieval uses bi-encoder embeddings (question → vector, chunk → vector,
  cosine/L2 similarity). This is fast but imprecise — the embedding captures
  general semantics, not whether the chunk actually *answers* the question.

  A cross-encoder reads the question AND a candidate chunk together and scores
  their relevance directly. It's 10-50x slower per pair than FAISS, but since
  we only rerank the top-K FAISS results (typically 20 → 5), the total cost
  is small (< 200ms on CPU for 20 pairs).

MODEL:
  cross-encoder/ms-marco-MiniLM-L-6-v2
  - 22M params, fast on CPU (~80ms for 20 pairs)
  - Trained on MS MARCO passage retrieval
  - Returns a relevance score (higher = more relevant, no fixed scale)

USAGE:
  reranker = Reranker()
  top_chunks = reranker.rerank(question, candidate_chunks, top_n=5)
"""

import logging

logger = logging.getLogger(__name__)

RERANKER_MODEL  = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_TOP_N   = 5      # chunks to return after reranking
DEFAULT_FETCH_K = 20     # how many to fetch from FAISS before reranking


class Reranker:

    def __init__(self, model_name: str = RERANKER_MODEL):
        from sentence_transformers import CrossEncoder
        logger.info("Loading reranker model: %s", model_name)
        self._model = CrossEncoder(model_name)

    def rerank(self, question: str, chunks: list[str], top_n: int = DEFAULT_TOP_N) -> list[str]:
        """
        Score each (question, chunk) pair with the cross-encoder.
        Returns the top_n chunks sorted by descending relevance score.

        chunks : list of plain text strings (already extracted from the chunk dicts)
        """
        if not chunks:
            return []

        if len(chunks) <= top_n:
            # Nothing to rerank — return as-is
            return chunks

        pairs  = [(question, c) for c in chunks]
        scores = self._model.predict(pairs)          # numpy array, one float per pair

        ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
        result = [chunk for _, chunk in ranked[:top_n]]

        logger.debug(
            "Reranker: %d → %d chunks (top score=%.3f, bottom=%.3f)",
            len(chunks), len(result),
            float(ranked[0][0]),
            float(ranked[min(top_n - 1, len(ranked) - 1)][0]),
        )
        return result
