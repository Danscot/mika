'''

this class defines the searhing through the faiss applying some weird vector stuffs

'''

import faiss

import numpy as np

from embedder import Embedder

from storage import Storage

from storage import Storage
from embedder import Embedder

class Search:
    """
    RAG Search class using FAISS + embedded chunks.
    """
    def __init__(self, index_path="index.faiss", chunks_path="chunks.pkl"):
        # Load FAISS index and chunks from storage
        self.storage = Storage()
        self.index = self.storage.load_index(index_path)
        self.chunks = self.storage.load_chunks(chunks_path)
        self.embedder = Embedder()

    def query(self, question: str, top_k: int = 5):
        """
        Search the FAISS index for the top_k most relevant chunks for a question.

        Returns:
            str: joined text of top_k chunks
        """
        # Encode the query into vector
        query_vec = self.embedder.embedder.encode(
            [question], convert_to_numpy=True
        )

        # Search FAISS
        distances, indices = self.index.search(query_vec, top_k)

        # Retrieve matching chunks
        results = []
        for i in indices[0]:
            chunk = self.chunks[i]
            if isinstance(chunk, dict) and "text" in chunk:
                results.append(chunk["text"])
            else:
                results.append(str(chunk))

        # Return top-k chunks joined as a single string
        return "\n".join(results)
