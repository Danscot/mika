
"""
This module is here to convert the crawl data into chunks
"""
class Chunker:

    def __init__(self, chunk_size: int = 1000):

        self.chunk_size = chunk_size

    def chunk_text(self, text: str):

        return [

            text[i : i + self.chunk_size] 

            for i in range(0, len(text), self.chunk_size)
        ]

    def chunk_docs(self, docs: list[str]):

        all_chunks = []

        for doc in docs:

            all_chunks.extend(self.chunk_text(doc))
            
        return [c.strip() for c in all_chunks if c.strip()]
