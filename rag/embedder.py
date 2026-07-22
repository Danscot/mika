"""
Purpose: Convert chunks into vector embeddings (weird math stuff).
"""

from sentence_transformers import SentenceTransformer


class Embedder:

    def __init__(self, model_name="all-MiniLM-L6-v2"):

        self.model_name = model_name

        self.embedder = SentenceTransformer(self.model_name)

    def embed(self, chunks):

        return self.embedder.encode(

            chunks,

            show_progress_bar=True,
            
            convert_to_numpy=True
        )
