"""
Builder Module
Purpose: Create the base knowledge index (FAISS + chunks).
"""

from crawler import Crawler

from chunker import Chunker

from embedder import Embedder

from indexer import Indexer

from storage import Storage


class Builder:

    def __init__(self):

        self.crawler = Crawler()

        self.chunker = Chunker()

        self.embedder = Embedder()

        self.storage = Storage()

    def build_base(self, url, index_path="index.faiss", chunks_path="chunks.pkl"):

        print(f"🔎 Crawling {url}...")

        docs = self.crawler.crawler_job(url)

        print("✂️ Chunking text...")

        chunks = self.chunker.chunk_docs(docs)

        print("🧮 Embedding chunks...")

        embeddings = self.embedder.embed(chunks)

         # ✅ Fix here: get embedding dimension
        dim = embeddings.shape[1]

        print(f"📦 Building FAISS index with dim={dim}...")

        indexer = Indexer(dim)
        
        index = indexer.build_index(embeddings)

        print("💾 Saving index + chunks...")
        self.storage.save_index(index, index_path)

        self.storage.save_chunks(chunks, chunks_path)

        print("✅ Base built successfully!")


if __name__ == "__main__":

    builder = Builder()

    builder.build_base("https://baileys.wiki/docs/intro/")
