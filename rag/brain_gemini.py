"""
brain_gemini.py
---------------
LLM layer — Google Gemini via the google-genai SDK.

Key improvements over v1:
  - Conversation history passed as structured message turns (not flattened into
    a prompt string), so the model can actually follow "tell me more about that"
    style references back to its own previous answers.
  - System prompt injected via the config.system_instruction field so it is
    processed by the model's instruction-tuning alignment, not mixed into the
    user turn.
  - Model is configurable via GEMINI_MODEL env var — change it anytime without
    touching code.

Env vars:
  GEMINI_API_KEY   — required
  GEMINI_MODEL     — model id (default: gemma-4-31b-it, change whenever you want)
"""

import logging
import os
import re
import sys

logger = logging.getLogger(__name__)


class BrainGemini:

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY is not set.")
            sys.exit(1)

        from google import genai
        from google.genai import types

        self._genai = genai
        self._types = types
        self.client = genai.Client(api_key=api_key)
        self.model  = os.environ.get("GEMINI_MODEL", "gemma-4-31b-it")
        logger.info("BrainGemini ready — model=%s", self.model)

    # ── public API ────────────────────────────────────────────────────────────

    def ask(self, prompt: str,
            history: list[dict] | None = None,
            system_prompt: str | None = None) -> dict:
        """
        Send a message to Gemini with optional conversation history.

        prompt        — the current user message (already includes RAG context)
        history       — list of {"role": "user"|"model", "text": str} dicts
                        representing previous turns in this conversation.
                        Passed as structured turns so the model can reference
                        its own earlier answers ("tell me more about that").
        system_prompt — injected via system_instruction, not as a user turn.

        Returns {"text": str, "code": str}
        """
        contents = self._build_contents(prompt, history or [])
        config   = self._build_config(system_prompt)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            raw = response.text or ""
        except Exception as exc:
            logger.exception("Gemini API error")
            raw = f"[Error communicating with Gemini: {exc}]"

        return self._parse(raw)

    def ask_stream(self, prompt: str,
                   history: list[dict] | None = None,
                   system_prompt: str | None = None):
        """
        Generator yielding text chunks as they stream from Gemini.
        Useful for future SSE streaming to the Telegram bot.
        """
        contents = self._build_contents(prompt, history or [])
        config   = self._build_config(system_prompt)

        try:
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            logger.exception("Gemini stream error")
            yield f"[Error: {exc}]"

    # ── internals ─────────────────────────────────────────────────────────────

    def _build_contents(self, prompt: str, history: list[dict]) -> list:
        """
        Build the contents list for the Gemini API.
        Each history entry becomes a properly-typed Content object so the model
        sees a real conversation transcript, not a flat string.
        """
        types    = self._types
        contents = []

        for turn in history:
            role = turn.get("role", "user")
            text = turn.get("text", "")
            # Gemini SDK expects "user" or "model" roles
            if role not in ("user", "model"):
                role = "user"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part(text=text)],
                )
            )

        # Current user message
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(text=prompt)],
            )
        )
        return contents

    def _build_config(self, system_prompt: str | None):
        """Build GenerateContentConfig with system instruction if provided."""
        types = self._types
        if system_prompt:
            return types.GenerateContentConfig(
                system_instruction=system_prompt,
            )
        return None

    def _parse(self, raw: str) -> dict:
        """Split response into prose text and code blocks."""
        code_blocks = re.findall(r"```(?:\w+\n)?(.*?)```", raw, re.DOTALL)
        text_clean  = re.sub(r"```(?:\w+\n)?.*?```", "", raw, flags=re.DOTALL).strip()
        return {
            "text": text_clean,
            "code": "\n\n".join(b.strip() for b in code_blocks),
        }
