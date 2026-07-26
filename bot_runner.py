"""
bot_runner.py
-------------
Runs ONE Telegram bot instance for a given bot config entry in bots.json.

This is the Python equivalent of a PM2 app entry.
Supervisor (or systemd) launches one process per bot:

    python bot_runner.py --bot-id <id>

Each process is fully isolated — its own event loop, its own MainGemini
session store, its own token. No shared state between bots, so no asyncio
thread conflicts.

Environment:
  DJANGO_SETTINGS_MODULE  (set automatically)
  GEMINI_API_KEY          (required)
  SSL_CERT_FILE           (set by this script via certifi)
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

# ── SSL fix (must happen before any network import) ───────────────────────────
import certifi
os.environ["SSL_CERT_FILE"]      = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# ── Django setup ──────────────────────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mika_project.settings")

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import django
django.setup()

from django.conf import settings

# ── RAG path ──────────────────────────────────────────────────────────────────
RAG_DIR = str(BASE_DIR / "rag")
if RAG_DIR not in sys.path:
    sys.path.insert(0, RAG_DIR)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("bot_runner")

# ── Imports after path setup ──────────────────────────────────────────────────
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from rag.main_gemini import MainGemini


# ═══════════════════════════════════════════════════════════════════════════════
#  Config loader
# ═══════════════════════════════════════════════════════════════════════════════

def load_bot_config(bot_id: str) -> dict:
    """Load a single bot's config from bots.json by ID."""
    bots_path = Path(settings.INDEX_DIR).parent / "bots.json"
    if not bots_path.exists():
        raise FileNotFoundError(f"bots.json not found at {bots_path}")

    with open(bots_path) as f:
        bots = json.load(f)

    for bot in bots:
        if bot["id"] == bot_id:
            return bot

    raise ValueError(f"No bot with id='{bot_id}' found in bots.json")


def list_available_indexes() -> list[str]:
    return sorted(p.stem for p in Path(settings.INDEX_DIR).glob("*.faiss"))


# ═══════════════════════════════════════════════════════════════════════════════
#  Bot class — one instance per process
# ═══════════════════════════════════════════════════════════════════════════════

class MikaBot:

    def __init__(self, config: dict):
        self.config  = config
        self.name    = config["name"]
        self.token   = config["token"]
        self.model   = config.get("model", "gemma-4-31b-it")
        self.prompt  = config.get("system_prompt", "")

        # Support both single index (legacy) and multiple indexes
        raw = config.get("index_names") or config.get("index_name", "default")
        self.indexes: list[str] = raw if isinstance(raw, list) else [raw]

        # Per-user session store (isolated to this process)
        self._sessions: dict[str, MainGemini] = {}

        logger.info(
            "[%s] Initialised — indexes=%s model=%s",
            self.name, self.indexes, self.model,
        )

    # ── Session management ────────────────────────────────────────────────────

    def _get_session(self, user_id: str) -> MainGemini | None:
        if user_id not in self._sessions:
            try:
                self._sessions[user_id] = MainGemini(
                    user_id=f"{self.config['id']}:{user_id}",
                    index_names=self.indexes,
                    system_prompt_override=self.prompt or None,
                )
                logger.info("[%s] New session for user %s (indexes=%s)", self.name, user_id, self.indexes)
            except FileNotFoundError as exc:
                logger.warning("[%s] %s", self.name, exc)
                return None
        return self._sessions[user_id]

    def _clear_session(self, user_id: str):
        self._sessions.pop(user_id, None)

    # ── Telegram handlers ─────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.message.from_user
        indexes = list_available_indexes()
        intro    = self.prompt or f"I'm {self.name}, your AI assistant."
        idx_list = ", ".join(f"`{i}`" for i in self.indexes)
        await update.message.reply_text(
            f"Hey {user.first_name}! 👋\n\n"
            f"{intro}\n\n"
            f"Searching across: {idx_list}\n\n"
            "Just ask me anything!",
            parse_mode="Markdown",
        )

    async def cmd_clear(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        self._clear_session(str(update.message.from_user.id))
        await update.message.reply_text("Memory cleared ✓ Fresh start!")

    async def cmd_index(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        idx_list = "\n".join(f"• `{i}`" for i in self.indexes)
        await update.message.reply_text(
            f"This bot searches across *{len(self.indexes)}* database(s):\n{idx_list}\n\n"
            "To change the connected databases, edit this bot in the dashboard.",
            parse_mode="Markdown",
        )

    async def cmd_indexes(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        available = list_available_indexes()
        if not available:
            await update.message.reply_text("No indexes available yet.")
        else:
            lines = "\n".join(f"• `{i}`{'  ← active' if i == self.index else ''}" for i in available)
            await update.message.reply_text(f"Available databases:\n{lines}", parse_mode="Markdown")

    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.message.from_user.id)
        text    = update.message.text.strip()

        await ctx.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing",
        )

        session = self._get_session(user_id)
        if session is None:
            await update.message.reply_text(
                f"The knowledge database *{self.index}* isn't available. "
                "Please contact the administrator.",
                parse_mode="Markdown",
            )
            return

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, session.query, text
            )
        except Exception as exc:
            logger.exception("[%s] Query failed for user %s", self.name, user_id)
            await update.message.reply_text(f"Something went wrong: {exc}")
            return

        if response.get("text"):
            for chunk in _split(response["text"], 4000):
                await update.message.reply_text(chunk)

        if response.get("code"):
            for chunk in _split(response["code"], 3800):
                await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")

    # ── Runner ────────────────────────────────────────────────────────────────

    def run(self):
        """Build and start the bot. Blocks until SIGTERM/SIGINT."""
        app = (
            ApplicationBuilder()
            .token(self.token)
            .concurrent_updates(True)   # handle multiple users concurrently
            .build()
        )

        app.add_handler(CommandHandler("start",   self.cmd_start))
        app.add_handler(CommandHandler("clear",   self.cmd_clear))
        app.add_handler(CommandHandler("index",   self.cmd_index))
        app.add_handler(CommandHandler("indexes", self.cmd_indexes))
        app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message,
        ))

        logger.info("[%s] Polling started (token=...%s)", self.name, self.token[-6:])
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,   # ignore messages that built up while offline
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Run a single Mika bot instance")
    parser.add_argument("--bot-id", required=True, help="Bot ID from bots.json")
    args = parser.parse_args()

    try:
        config = load_bot_config(args.bot_id)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Cannot load bot config: %s", exc)
        sys.exit(1)

    if not os.environ.get("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY is not set")
        sys.exit(1)

    bot = MikaBot(config)

    # Graceful shutdown on SIGTERM (sent by supervisor/systemd when stopping)
    def _shutdown(signum, frame):
        logger.info("[%s] Received signal %s — shutting down", bot.name, signum)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("[%s] Stopped by keyboard interrupt", bot.name)


if __name__ == "__main__":
    main()
