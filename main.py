"""
Bailey Bot Core
Purpose: Provide RAG-style query handling using FAISS index + embeddings.
"""

import faiss
import numpy as np

from embedder import Embedder
from storage import Storage


class BaileyBot:
    def __init__(self, index_path="index.faiss", chunks_path="chunks.pkl"):
        self.storage = Storage()
        self.index = self.storage.load_index(index_path)
        self.chunks = self.storage.load_chunks(chunks_path)
        self.embedder = Embedder()

    def query(self, question: str, top_k: int = 5):
        # Encode the query
        query_vec = self.embedder.embedder.encode([question], convert_to_numpy=True)

        # Search FAISS
        distances, indices = self.index.search(query_vec, top_k)

        # Retrieve matching chunks
        results = [self.chunks[i] for i in indices[0]]

        return results


if __name__ == "__main__":
    bot = BaileyBot()
    q = "What is Bailey library about?"
    context = bot.query(q)
    print("Top results:")
    for c in context:
        print("----")
        print(c)
