from storage import Storage

from embedder import Embedder

import numpy as np

class Search:
    """
    RAG Search class using FAISS + embedded chunks.
    Filters out chunks that are not similar enough.
    """
    def __init__(self, index_path="index.faiss", chunks_path="chunks.pkl", threshold=0.8):

        self.storage = Storage()

        self.index = self.storage.load_index(index_path)

        self.chunks = self.storage.load_chunks(chunks_path)

        self.embedder = Embedder()

        self.threshold = threshold  # Similarity threshold for FAISS results

    def query(self, question: str, top_k: int = 5):
        """
        Search the FAISS index for the top_k most relevant chunks for a question.
        Returns a joined string of only the sufficiently similar chunks.
        """
        # Encode the question
        query_vec = self.embedder.embedder.encode([question], convert_to_numpy=True)

        # Search FAISS
        distances, indices = self.index.search(query_vec, top_k)

        # Filter by similarity threshold (for L2 distance, lower is better)
        results = []

        for dist, i in zip(distances[0], indices[0]):

            if dist <= self.threshold:

                chunk = self.chunks[i]

                if isinstance(chunk, dict) and "text" in chunk:

                    results.append(chunk["text"])

                else:
                    
                    results.append(str(chunk))

        # Return joined text, or empty string if nothing relevant
        return "\n".join(results)
