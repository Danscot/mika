import logging
import numpy as np
from storage import Storage
from embedder import Embedder

logger = logging.getLogger(__name__)


class Search:
    """
    RAG Search class using FAISS + embedded chunks.

    Uses L2 (Euclidean) distance — LOWER distance means MORE similar.
    The default threshold of 1.5 is appropriate for all-MiniLM-L6-v2:
      • Very similar chunks:   ~0.0 – 0.5
      • Loosely related:       ~0.5 – 1.5
      • Unrelated:             > 1.5

    The old default of 0.8 was too strict, silently dropping all results
    and causing the AI to say "I don't know" even after ingestion.
    """

    def __init__(self, index_path="index.faiss", chunks_path="chunks.pkl", threshold=1.5):
        self.storage   = Storage()
        self.index     = self.storage.load_index(index_path)
        self.chunks    = self.storage.load_chunks(chunks_path)
        self.embedder  = Embedder()
        self.threshold = threshold

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
            "RAG distances for %r: %s", question, list(zip(distances[0], indices[0]))
        )

        results = []
        for dist, i in zip(distances[0], indices[0]):
            if i == -1:          # FAISS returns -1 for empty slots
                continue
            if dist <= self.threshold:
                chunk = self.chunks[i]
                text  = chunk["text"] if isinstance(chunk, dict) and "text" in chunk else str(chunk)
                results.append(text)

        if not results:
            logger.warning(
                "RAG returned 0 chunks for %r (best distance=%.3f, threshold=%.3f). "
                "Consider raising the threshold or re-ingesting the data.",
                question,
                float(distances[0][0]) if len(distances[0]) else -1,
                self.threshold,
            )

        return "\n\n".join(results)
