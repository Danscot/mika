"""
main_gemini.py
--------------
Orchestrates RAG search + memory + Gemini brain.
Drop-in replacement for main.py — same .query() interface.

The index_name determines which .faiss / .pkl pair is loaded.
It resolves paths via INDEX_DIR from Django settings when run inside
Django, or falls back to a plain ./indexes/ folder when run standalone.

Hot-reload behaviour
--------------------
self.rag is NOT held forever. On every call to query(), we check whether
the .faiss file on disk has been modified since the last load (via mtime).
If it has, we reload Search from disk before querying.  This means a new
append via the web UI is visible to the bot on the very next message —
no server restart required.
"""

import json
import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_index_dir() -> Path:
    try:
        from django.conf import settings
        return Path(settings.INDEX_DIR)
    except Exception:
        return Path(__file__).parent.parent / "indexes"


def _resolve_rag_dir() -> Path:
    try:
        from django.conf import settings
        return Path(settings.RAG_DIR)
    except Exception:
        return Path(__file__).parent


class MainGemini:

    def __init__(self, user_id: str = "default", index_name: str = "default"):
        # Make sure the RAG scripts are importable
        rag_dir = str(_resolve_rag_dir())
        if rag_dir not in sys.path:
            sys.path.insert(0, rag_dir)

        from memory       import Memory
        from brain_gemini import BrainGemini

        index_dir = _resolve_index_dir()
        self._index_path  = str(index_dir / f"{index_name}.faiss")
        self._chunks_path = str(index_dir / f"{index_name}.pkl")

        if not Path(self._index_path).exists():
            raise FileNotFoundError(
                f"Index '{index_name}' not found at {self._index_path}. "
                "Ingest some data first via the web UI."
            )

        self.brain  = BrainGemini()
        self.memory = Memory(user_id=user_id)

        # Load persona
        persona_path = Path(__file__).parent / "persona.json"
        if persona_path.exists():
            with open(persona_path, "r", encoding="utf-8") as f:
                self.persona = json.load(f).get("persona", "")
        else:
            self.persona = "You are Mika, a helpful AI assistant."

        # Load the searcher for the first time
        self._rag_mtime: float = 0.0
        self._rag = None
        self._load_rag()

    # ── RAG hot-reload ────────────────────────────────────────────────────────

    def _load_rag(self):
        """(Re)load the Search instance from disk and record the index mtime."""
        from searcher import Search
        logger.info("Loading RAG index from %s", self._index_path)
        self._rag = Search(
            index_path=self._index_path,
            chunks_path=self._chunks_path,
        )
        self._rag_mtime = Path(self._index_path).stat().st_mtime

    def _rag_is_stale(self) -> bool:
        """Return True if the .faiss file on disk is newer than our loaded copy."""
        try:
            current_mtime = Path(self._index_path).stat().st_mtime
            return current_mtime > self._rag_mtime
        except OSError:
            return False

    @property
    def rag(self):
        """Always returns an up-to-date Search instance."""
        if self._rag_is_stale():
            logger.info(
                "Index '%s' has changed on disk — reloading RAG (no restart needed).",
                self._index_path,
            )
            self._load_rag()
        return self._rag

    # ── public API ────────────────────────────────────────────────────────────

    def query(self, question: str) -> dict:
        """
        Full RAG pipeline:
          1. Check if the index has been updated on disk → reload if so
          2. Retrieve relevant doc chunks from FAISS
          3. Retrieve relevant past conversations from memory
          4. Build prompt with persona + context + memory
          5. Ask Gemini
          6. Save Q&A to memory
          7. Return {"text": ..., "code": ...}
        """
        # self.rag automatically reloads if the index file was updated
        context = self.rag.query(question)

        past = self.memory.query(question)
        memory_str = "".join(
            f"Q: {c['question']}\nA: {c['answer']}\n" for c in past
        )

        prompt = f"""
{self.persona}

Context (from knowledge base):
{context if context else "No relevant context found."}

Past conversation memory:
{memory_str if memory_str else "No prior conversations."}

User question:
{question}
""".strip()

        answer = self.brain.ask(prompt)
        self.memory.add_conversation(question, answer["text"])
        return answer
