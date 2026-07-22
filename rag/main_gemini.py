"""
main_gemini.py
--------------
Orchestrates RAG search + memory + Gemini brain.
Drop-in replacement for main.py — same .query() interface.

The index_name determines which .faiss / .pkl pair is loaded.
It resolves paths via INDEX_DIR from Django settings when run inside
Django, or falls back to a plain ./indexes/ folder when run standalone.
"""

import json
import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_index_dir() -> Path:
    """
    Try to get INDEX_DIR from Django settings.
    If Django isn't configured, fall back to ./indexes/ next to this file.
    """
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

        from searcher import Search
        from memory   import Memory
        from brain_gemini import BrainGemini

        index_dir   = _resolve_index_dir()
        index_path  = str(index_dir / f"{index_name}.faiss")
        chunks_path = str(index_dir / f"{index_name}.pkl")

        if not Path(index_path).exists():
            raise FileNotFoundError(
                f"Index '{index_name}' not found at {index_path}. "
                "Ingest some data first via the web UI."
            )

        self.rag    = Search(index_path=index_path, chunks_path=chunks_path)
        self.brain  = BrainGemini()
        self.memory = Memory(user_id=user_id)

        # Load persona
        persona_path = Path(__file__).parent / "persona.json"
        if persona_path.exists():
            with open(persona_path, "r", encoding="utf-8") as f:
                self.persona = json.load(f).get("persona", "")
        else:
            self.persona = "You are Mika, a helpful AI assistant."

    def query(self, question: str) -> dict:
        """
        Full RAG pipeline:
          1. Retrieve relevant doc chunks from FAISS
          2. Retrieve relevant past conversations from memory
          3. Build prompt with persona + context + memory
          4. Ask Gemini
          5. Save Q&A to memory
          6. Return {"text": ..., "code": ...}
        """
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

        # answer is {"text": ..., "code": ...}
        # Store the text part in memory
        self.memory.add_conversation(question, answer["text"])

        return answer
