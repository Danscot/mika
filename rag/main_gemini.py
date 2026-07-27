"""
main_gemini.py
--------------
Orchestrates the full RAG pipeline:
  Embedder (shared) → FAISS retrieval → Cross-encoder reranking
  → Gemini with structured message history → Memory (sliding window)

Changes from previous version:
  1. Reranker loaded once and shared across all Search instances
  2. Conversation history passed to Gemini as structured turns (not flat string)
     so "tell me more" / "what about the second point" work correctly
  3. System prompt injected via system_instruction (not mixed into user turn)
  4. RAG context injected into the user message, keeping it separate from history
"""

import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _resolve_memory_dir() -> Path:
    return _resolve_index_dir().parent / "user_indexes"


# ─────────────────────────────────────────────────────────────────────────────

class MultiSearch:
    """Queries multiple Search instances in parallel and merges results."""

    def __init__(self, searchers: list):
        self.searchers = searchers

    def query(self, question: str, top_k: int = 5) -> str:
        results = []
        with ThreadPoolExecutor(max_workers=len(self.searchers)) as pool:
            futures = {pool.submit(s.query, question, top_k): s for s in self.searchers}
            for fut in as_completed(futures):
                try:
                    text = fut.result()
                    if text:
                        results.append(text)
                except Exception as exc:
                    logger.warning("MultiSearch error: %s", exc)
        return "\n\n---\n\n".join(results)


# ─────────────────────────────────────────────────────────────────────────────

class MainGemini:

    def __init__(self, user_id: str = "default",
                 index_name:  str | None = None,
                 index_names: list[str] | None = None,
                 system_prompt_override: str | None = None):

        rag_dir = str(_resolve_rag_dir())
        if rag_dir not in sys.path:
            sys.path.insert(0, rag_dir)

        from embedder     import Embedder
        from reranker     import Reranker
        from searcher     import Search
        from memory       import Memory
        from brain_gemini import BrainGemini

        index_dir = _resolve_index_dir()

        # Resolve index list
        if index_names:
            self._index_names = index_names
        elif index_name:
            self._index_names = [index_name]
        else:
            self._index_names = ["default"]

        for name in self._index_names:
            p = index_dir / f"{name}.faiss"
            if not p.exists():
                raise FileNotFoundError(
                    f"Index '{name}' not found at {p}. "
                    "Ingest some data first via the web UI."
                )

        self._index_dir = index_dir

        # ── Shared heavy objects (loaded once per session) ─────────────────
        logger.info("Loading embedder…")
        self._embedder = Embedder()

        logger.info("Loading reranker…")
        self._reranker = Reranker()

        # Primary index for mtime hot-reload tracking
        self._primary_faiss = str(index_dir / f"{self._index_names[0]}.faiss")
        self._rag_mtime: float = 0.0
        self._rag = None
        self._load_rag()

        # Memory and brain
        self.memory = Memory(
            user_id=user_id,
            index_dir=str(_resolve_memory_dir()),
        )
        self.brain = BrainGemini()

        # Persona / system prompt
        if system_prompt_override:
            self.persona = system_prompt_override
        else:
            persona_path = Path(__file__).parent / "persona.json"
            if persona_path.exists():
                with open(persona_path, encoding="utf-8") as f:
                    self.persona = json.load(f).get("persona", "")
            else:
                self.persona = "You are Mika, a helpful AI assistant."

    # ── RAG hot-reload ────────────────────────────────────────────────────────

    def _load_rag(self):
        from searcher import Search

        def _make(name: str) -> Search:
            return Search(
                index_path=str(self._index_dir / f"{name}.faiss"),
                chunks_path=str(self._index_dir / f"{name}.pkl"),
                embedder=self._embedder,
                reranker=self._reranker,
            )

        if len(self._index_names) == 1:
            logger.info("Loading RAG index: %s", self._index_names[0])
            self._rag = _make(self._index_names[0])
        else:
            logger.info("Loading %d RAG indexes: %s", len(self._index_names), self._index_names)
            self._rag = MultiSearch([_make(n) for n in self._index_names])

        self._rag_mtime = Path(self._primary_faiss).stat().st_mtime

    def _rag_stale(self) -> bool:
        try:
            return Path(self._primary_faiss).stat().st_mtime > self._rag_mtime
        except OSError:
            return False

    @property
    def rag(self):
        if self._rag_stale():
            logger.info("Index changed — hot-reloading RAG")
            self._load_rag()
        return self._rag

    # ── Query pipeline ────────────────────────────────────────────────────────

    def query(self, question: str) -> dict:
        """
        Pipeline:
          1. RAG retrieval + reranking (concurrent with memory lookup)
          2. Build user message with RAG context injected
          3. Pass conversation history as structured turns to Gemini
          4. Persist Q+A turn to sliding-window memory
        """
        rag = self.rag

        # Run RAG and memory lookup concurrently
        with ThreadPoolExecutor(max_workers=2) as pool:
            rag_fut    = pool.submit(rag.query,         question)
            memory_fut = pool.submit(self.memory.query, question)
            context    = rag_fut.result()
            past_turns = memory_fut.result()

        # Build the user message: question + RAG context injected inline.
        # The context is part of the user message, NOT the system prompt,
        # so the model treats it as provided evidence rather than instructions.
        if context:
            user_message = (
                f"{question}\n\n"
                f"[Relevant knowledge base context]\n{context}"
            )
        else:
            user_message = question

        # Convert sliding-window turns into Gemini message format:
        #   {"role": "user"|"model", "text": str}
        # This lets the model reference its own earlier answers directly.
        history = []
        for turn in past_turns:
            history.append({"role": "user",  "text": turn["question"]})
            history.append({"role": "model", "text": turn["answer"]})

        # Call Gemini with structured history + system prompt
        answer = self.brain.ask(
            prompt=user_message,
            history=history,
            system_prompt=self.persona or None,
        )

        # Persist Q+A to memory (fast JSON write, no embedding)
        self.memory.add_conversation(question, answer.get("text", ""))

        return answer
