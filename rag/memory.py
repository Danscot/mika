"""
memory.py
---------
Lightweight conversation memory using a simple sliding window.

WHY NOT FAISS FOR MEMORY:
  The old implementation embedded every Q+A pair into a FAISS index,
  wrote it to disk after every message, and ran a vector search to
  retrieve "relevant" past turns. For 5-50 messages per user this is
  massive overkill:
    - Loads sentence-transformers twice (once in Memory, once in Search)
    - Blocks on disk I/O (faiss.write_index + pickle.dump) after every reply
    - Vector similarity on 10 conversation turns is not meaningfully better
      than just keeping the last N turns — recent context IS the relevant context

WHAT WE DO INSTEAD:
  Keep the last MAX_TURNS Q+A pairs in a plain Python list (in memory).
  Optionally persist to a tiny JSON file so memory survives bot restarts.
  Zero embedding, zero FAISS, zero disk I/O on the hot path.
"""

import json
import logging
import os
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_TURNS = 10          # how many Q+A pairs to keep per user
PERSIST   = True        # save to disk so memory survives restarts


class Memory:

    def __init__(self, user_id: str, index_dir: str = "user_indexes"):
        self.user_id   = user_id
        self._data_dir = Path(index_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._path     = self._data_dir / f"{user_id}_memory.json"
        self._turns: deque[dict] = deque(maxlen=MAX_TURNS)

        # Load persisted memory if it exists
        if PERSIST and self._path.exists():
            try:
                with open(self._path) as f:
                    saved = json.load(f)
                for turn in saved[-MAX_TURNS:]:
                    self._turns.append(turn)
                logger.debug("Loaded %d turns for user %s", len(self._turns), user_id)
            except Exception as e:
                logger.warning("Could not load memory for %s: %s", user_id, e)

    # ── public API (same interface as the old Memory) ─────────────────────────

    def add_conversation(self, question: str, answer: str):
        """Append a Q+A turn. O(1), no embedding, no FAISS."""
        self._turns.append({"question": question, "answer": answer})
        if PERSIST:
            self._save()

    def query(self, query_text: str = "", top_k: int = 5) -> list[dict]:
        """
        Return the most recent min(top_k, MAX_TURNS) turns.
        query_text is accepted for interface compatibility but ignored —
        recency is a better signal than similarity for conversation context.
        """
        turns = list(self._turns)
        return turns[-top_k:]

    def clear(self, user_id: str | None = None):
        """Clear memory for this user."""
        self._turns.clear()
        if PERSIST and self._path.exists():
            self._path.unlink(missing_ok=True)

    # ── internal ──────────────────────────────────────────────────────────────

    def _save(self):
        try:
            with open(self._path, "w") as f:
                json.dump(list(self._turns), f)
        except Exception as e:
            logger.warning("Could not persist memory for %s: %s", self.user_id, e)
