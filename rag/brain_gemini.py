"""
brain_gemini.py
---------------
LLM layer using Google AI Studio (Gemini) via the google-genai SDK.
Replaces the original brain.py (OpenRouter/Mistral).

Env vars required:
  GEMINI_API_KEY  — your Google AI Studio API key
  GEMINI_MODEL    — model id (default: gemma-4-31b-it)
"""

import os
import re
import sys
import logging

logger = logging.getLogger(__name__)


class BrainGemini:

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY is not set.")
            sys.exit(1)

        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model  = os.environ.get("GEMINI_MODEL", "gemma-4-31b-it")

    # ── public API ────────────────────────────────────────────────────────────

    def ask(self, prompt: str) -> dict:
        """
        Send prompt to Gemini and return {"text": ..., "code": ...}.
        Streams internally so the first token arrives fast; the full
        response is assembled before returning (Telegram can't stream anyway).
        """
        full_text = self._stream(prompt)
        return self._parse(full_text)

    def ask_stream(self, prompt: str):
        """
        Generator that yields raw text chunks as they arrive from Gemini.
        Use this if you want true streaming in the future (e.g. via SSE).
        """
        try:
            response = self.client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            logger.exception("Gemini stream error")
            yield f"[ERROR] {exc}"

    # ── internals ─────────────────────────────────────────────────────────────

    def _stream(self, prompt: str) -> str:
        """Consume the stream and return the full assembled response."""
        parts = []
        for chunk in self.ask_stream(prompt):
            parts.append(chunk)
        return "".join(parts)

    def _parse(self, raw: str) -> dict:
        """
        Split the model response into prose text and code blocks.
        Returns {"text": str, "code": str}.
        Code blocks (```...```) are extracted; everything else is text.
        """
        code_blocks = re.findall(r"```(?:\w+\n)?(.*?)```", raw, re.DOTALL)
        text_clean  = re.sub(r"```(?:\w+\n)?.*?```", "", raw, flags=re.DOTALL).strip()

        return {
            "text": text_clean,
            "code": "\n\n".join(b.strip() for b in code_blocks),
        }
