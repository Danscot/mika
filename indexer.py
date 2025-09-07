
import faiss
"""
Purpose: create or update FAISS index.
"""
class Indexer:

    def __init__(self, dim: int):

        self.index = faiss.IndexFlatL2(dim)

    def build_index(self, embeddings):

        self.index.add(embeddings)

        return self.index

    def append_to_index(self, new_embeddings):

        self.index.add(new_embeddings)

        return self.index


