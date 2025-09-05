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

    def __init__(self, api_key="", limit=50):

        self.crawler = Crawler()

        self.crawler.api = api_key

        self.crawler.limit = limit

        self.chunker = Chunker()

        self.embedder = Embedder()

        self.storage = Storage()

    def build_base(self, url, index_path="index.faiss", chunks_path="chunks.pkl"):

        print(f"🔎 Crawling {url}...")

        docs = self.crawler.crawler_job(url)

        print("✂️ Chunking text...")

        chunks = self.chunker.chunk_doc(docs)

        print("🧮 Embedding chunks...")

        embeddings = self.embedder.embed(chunks)


        print("📦 Building FAISS index...")

        indexer = Indexer(embeddings)

        index = indexer.build_index()

        print("💾 Saving index + chunks...")

        self.storage.save_index(index, index_path)

        self.storage.save_chunks(chunks, chunks_path)

        print("✅ Base built successfully!")


if __name__ == "__main__":

    builder = Builder(api_key="fc-46954301e4ff46e3a6bcc3bf3aafc320")

    builder.build_base("https://baileys.wiki/docs/intro/")
