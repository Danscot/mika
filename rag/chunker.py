"""
chunker.py
----------
Sentence-aware chunking using NLTK.

WHY SENTENCE-AWARE:
  The old character-split chunker would cut mid-sentence, producing fragments
  like "...the main cause of this phenome" / "non is attributed to...".
  FAISS embeds those broken fragments and scores them poorly — which is why
  the similarity threshold had to be as high as 1.8.

  Sentence-aware chunking keeps sentences whole, groups them into target-size
  windows, and overlaps by whole sentences. This produces cleaner embeddings
  and better retrieval scores.

NLTK setup (one-time):
  The first run downloads punkt_tab (~13 MB). Subsequent runs use the cache.
  Or pre-download: python -c "import nltk; nltk.download('punkt_tab')"
"""

import logging
import re

logger = logging.getLogger(__name__)

# Target sizes in characters (not tokens — fast to compute, good enough)
DEFAULT_CHUNK_SIZE = 800    # ~200 tokens for MiniLM
DEFAULT_OVERLAP    = 2      # sentences of overlap between chunks


def _ensure_nltk():
    """Download punkt_tab tokenizer data if not already present."""
    try:
        import nltk
        try:
            nltk.data.find("tokenizers/punkt_tab")
        except LookupError:
            logger.info("Downloading NLTK punkt_tab tokenizer…")
            nltk.download("punkt_tab", quiet=True)
        return True
    except ImportError:
        return False


def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences.
    Uses NLTK if available, falls back to a simple regex splitter.
    """
    if _ensure_nltk():
        import nltk
        return nltk.sent_tokenize(text)

    # Fallback: split on . ! ? followed by whitespace + capital letter
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [p.strip() for p in parts if p.strip()]


class Chunker:

    def __init__(self,
                 chunk_size: int = DEFAULT_CHUNK_SIZE,
                 overlap:    int = DEFAULT_OVERLAP):
        """
        chunk_size : target characters per chunk (soft limit — never cuts mid-sentence)
        overlap    : number of sentences to repeat at the start of the next chunk
        """
        self.chunk_size = chunk_size
        self.overlap    = overlap

    # ── public API ────────────────────────────────────────────────────────────

    def chunk_text(self, text: str, source: str = "") -> list[dict]:
        """
        Split text into sentence-aware, overlapping chunk dicts.
        Each chunk: {"text": str, "source": str}
        """
        text = text.strip()
        if not text:
            return []

        sentences = _split_sentences(text)
        if not sentences:
            return []

        chunks  = []
        window  = []       # current window of sentences
        win_len = 0        # character count of current window

        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue

            # If adding this sentence would overflow, flush the current window
            if win_len + len(sent) > self.chunk_size and window:
                body = " ".join(window).strip()
                if body:
                    chunks.append({"text": body, "source": source})

                # Keep the last `overlap` sentences as the start of the next chunk
                window  = window[-self.overlap:] if self.overlap else []
                win_len = sum(len(s) + 1 for s in window)

            window.append(sent)
            win_len += len(sent) + 1   # +1 for the space separator

        # Flush remaining sentences
        if window:
            body = " ".join(window).strip()
            if body:
                chunks.append({"text": body, "source": source})

        logger.debug("chunk_text: %d sentences → %d chunks (source=%r)", len(sentences), len(chunks), source)
        return chunks

    def chunk_docs(self, docs: list, source: str = "") -> list[dict]:
        """
        Accept a list of strings or dicts ({"text": ..., "source": ...})
        and return a flat list of chunk dicts.
        """
        all_chunks: list[dict] = []

        for doc in docs:
            if isinstance(doc, dict):
                text = doc.get("text", "")
                src  = doc.get("source", source)
            else:
                text = str(doc)
                src  = source

            all_chunks.extend(self.chunk_text(text, source=src))

        return all_chunks
