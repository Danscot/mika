'''

this class defines the searhing through the faiss applying some weird vector stuffs

'''

import faiss

import numpy as np

from embedder import Embedder

from storage import Storage


class Search:

	
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

        return "\n".join(results)
        