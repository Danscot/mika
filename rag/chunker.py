"""
chunker.py
----------
Converts raw text / crawled docs into chunk dicts:
  {"text": str, "source": str}

Storing dicts (instead of bare strings) makes it easy to add source
attribution later and avoids the isinstance branch in searcher.py.
"""


class Chunker:

    def __init__(self, chunk_size: int = 1000, overlap: int = 100):
        """
        chunk_size : target characters per chunk
        overlap    : characters of overlap between consecutive chunks
                     (helps avoid cutting a sentence right at a boundary)
        """
        self.chunk_size = chunk_size
        self.overlap    = overlap

    # ── public API ────────────────────────────────────────────────────────────

    def chunk_text(self, text: str, source: str = "") -> list[dict]:
        """Split a single text string into overlapping chunk dicts."""
        chunks = []
        start  = 0
        length = len(text)

        while start < length:
            end  = min(start + self.chunk_size, length)
            body = text[start:end].strip()
            if body:
                chunks.append({"text": body, "source": source})
            start += self.chunk_size - self.overlap   # advance with overlap

        return chunks

    def chunk_docs(self, docs: list, source: str = "") -> list[dict]:
        """
        Accept a list of strings or dicts ({"text": ..., "source": ...})
        and return a flat list of chunk dicts.
        """
        all_chunks: list[dict] = []

        for doc in docs:
            if isinstance(doc, dict):
                text   = doc.get("text", "")
                src    = doc.get("source", source)
            else:
                text = str(doc)
                src  = source

            all_chunks.extend(self.chunk_text(text, source=src))

        return all_chunks
