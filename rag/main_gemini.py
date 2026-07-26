"""
main_gemini.py
--------------
Orchestrates RAG search + memory + Gemini brain.

Performance improvements over v1:
  - Single Embedder instance shared across all Search objects in a session
    (avoids loading the 90MB sentence-transformers model multiple times)
  - RAG search and memory lookup run concurrently via ThreadPoolExecutor
  - Memory is a lightweight sliding window (no FAISS, no disk I/O on hot path)
  - Index hot-reload via mtime check — no restart needed after ingestion
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
    """Memory JSON files live next to the indexes."""
    return _resolve_index_dir().parent / "user_indexes"


# ─────────────────────────────────────────────────────────────────────────────

class MultiSearch:
    """
    Queries multiple Search instances in parallel and merges results.
    Each searcher already uses the shared embedder so there is no
    redundant model loading.
    """

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
        """
        index_names  – list of index names to search (preferred)
        index_name   – single index name (legacy alias)
        """
        rag_dir = str(_resolve_rag_dir())
        if rag_dir not in sys.path:
            sys.path.insert(0, rag_dir)

        from embedder     import Embedder
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

        # Validate
        for name in self._index_names:
            p = index_dir / f"{name}.faiss"
            if not p.exists():
                raise FileNotFoundError(
                    f"Index '{name}' not found at {p}. "
                    "Ingest some data first via the web UI."
                )

        # ── Single shared embedder ─────────────────────────────────────────
        # All Search objects in this session use the same Embedder instance,
        # so the sentence-transformers model is only loaded once into RAM.
        self._embedder = Embedder()
        self._index_dir = index_dir

        # Primary index for mtime tracking (hot-reload)
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

        # Persona
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

        def _make_search(name: str) -> Search:
            return Search(
                index_path=str(self._index_dir / f"{name}.faiss"),
                chunks_path=str(self._index_dir / f"{name}.pkl"),
                embedder=self._embedder,   # ← shared instance
            )

        if len(self._index_names) == 1:
            logger.info("Loading RAG index: %s", self._index_names[0])
            self._rag = _make_search(self._index_names[0])
        else:
            logger.info("Loading %d RAG indexes: %s", len(self._index_names), self._index_names)
            self._rag = MultiSearch([_make_search(n) for n in self._index_names])

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
          1. RAG search + memory lookup run concurrently
          2. Build prompt
          3. Call Gemini
          4. Persist Q+A to memory (non-blocking write)
        """
        rag   = self.rag   # resolve once (may hot-reload)

        # Run RAG search and memory lookup at the same time
        with ThreadPoolExecutor(max_workers=2) as pool:
            rag_fut    = pool.submit(rag.query,         question)
            memory_fut = pool.submit(self.memory.query, question)

            context    = rag_fut.result()
            past_turns = memory_fut.result()

        # Format memory as a short conversation transcript
        memory_str = "".join(
            f"User: {t['question']}\nAssistant: {t['answer']}\n"
            for t in past_turns
        )

        prompt = f"""\
{self.persona}

### Knowledge base context
{context or "No relevant context found."}

### Recent conversation
{memory_str or "No prior conversation."}

### User message
{question}""".strip()

        answer = self.brain.ask(prompt)

        # Persist to memory — the sliding window write is fast (JSON, no embedding)
        self.memory.add_conversation(question, answer.get("text", ""))

        return answer
