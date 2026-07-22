"""
bot.py
------
Telegram bot for Mika — powered by Gemini + FAISS knowledge base.

Runs alongside the Django project (see run.py).

Env vars:
  TELEGRAM_TOKEN   — bot token from @BotFather
  GEMINI_API_KEY   — Google AI Studio key
  GEMINI_MODEL     — model id (default: gemma-4-31b-it)
  DEFAULT_INDEX    — which FAISS index to query (default: "default")
  DJANGO_SETTINGS_MODULE — set automatically by run.py

Commands:
  /start              — greeting
  /index <name>       — switch to a different knowledge index mid-session
  /indexes            — list available indexes
  /clear              — clear your conversation memory
"""

import os
import sys
import logging
import asyncio
from pathlib import Path

# ── Make sure Django settings are loaded so _resolve_index_dir works ──────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mika_project.settings")
try:
    import django
    django.setup()
except Exception:
    pass  # Running outside Django — path fallback kicks in

# ── Add rag/ to sys.path ──────────────────────────────────────────────────────
RAG_DIR = Path(__file__).parent / "rag"
if str(RAG_DIR) not in sys.path:
    sys.path.insert(0, str(RAG_DIR))

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from rag.main_gemini import MainGemini

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Session store: user_id → MainGemini instance ──────────────────────────────
sessions: dict[str, MainGemini] = {}


def get_session(user_id: str, index_name: str = None) -> MainGemini | None:
    """Return existing session or create a new one. Returns None on error."""
    key = f"{user_id}:{index_name or 'default'}"
    if key not in sessions:
        try:
            idx = index_name or os.environ.get("DEFAULT_INDEX", "default")
            sessions[key] = MainGemini(user_id=user_id, index_name=idx)
            logger.info("Created session for user %s with index '%s'", user_id, idx)
        except FileNotFoundError as exc:
            logger.warning(str(exc))
            return None
    return sessions[key]


def list_available_indexes() -> list[str]:
    """List .faiss files in the indexes directory."""
    try:
        from django.conf import settings
        idx_dir = Path(settings.INDEX_DIR)
    except Exception:
        idx_dir = Path(__file__).parent / "indexes"
    return sorted(p.stem for p in idx_dir.glob("*.faiss"))


# ── Handlers ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    available = list_available_indexes()

    if not available:
        await update.message.reply_text(
            "Hey! I'm Mika 👋\n\n"
            "No knowledge index found yet. Go to the web UI and ingest some data first, "
            "then come back and ask me anything!"
        )
        return

    default = os.environ.get("DEFAULT_INDEX", "default")
    greeting = (
        f"Hey {user.first_name}! I'm Mika 👋\n\n"
        f"I'm loaded with the *{default}* knowledge base.\n"
        f"Available indexes: {', '.join(f'`{i}`' for i in available)}\n\n"
        "Switch with /index <name> — or just ask me anything!"
    )
    await update.message.reply_text(greeting, parse_mode="Markdown")


async def cmd_indexes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    available = list_available_indexes()
    if not available:
        await update.message.reply_text("No indexes found. Ingest some data first via the web UI.")
    else:
        lines = "\n".join(f"• `{i}`" for i in available)
        await update.message.reply_text(f"Available indexes:\n{lines}", parse_mode="Markdown")


async def cmd_index(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Switch the current user's active index."""
    if not context.args:
        await update.message.reply_text("Usage: /index <name>")
        return

    user_id    = str(update.message.from_user.id)
    index_name = context.args[0].strip()
    session    = get_session(user_id, index_name)

    if session is None:
        available = list_available_indexes()
        await update.message.reply_text(
            f"Index `{index_name}` not found.\n"
            f"Available: {', '.join(f'`{i}`' for i in available) or 'none yet'}",
            parse_mode="Markdown",
        )
        return

    # Store the chosen index in user_data so handle_message picks it up
    context.user_data["index"] = index_name
    await update.message.reply_text(f"Switched to index `{index_name}` ✓", parse_mode="Markdown")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear this user's session (resets conversation memory)."""
    user_id    = str(update.message.from_user.id)
    index_name = context.user_data.get("index", os.environ.get("DEFAULT_INDEX", "default"))
    key        = f"{user_id}:{index_name}"
    sessions.pop(key, None)
    await update.message.reply_text("Memory cleared. Fresh start ✓")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id    = str(update.message.from_user.id)
    text       = update.message.text.strip()
    index_name = context.user_data.get("index", os.environ.get("DEFAULT_INDEX", "default"))

    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing",
    )

    session = get_session(user_id, index_name)

    if session is None:
        await update.message.reply_text(
            f"No index named `{index_name}` found. "
            "Ingest some data first via the web UI, or pick an index with /indexes.",
            parse_mode="Markdown",
        )
        return

    try:
        response = session.query(text)  # {"text": ..., "code": ...}
    except Exception as exc:
        logger.exception("Query failed for user %s", user_id)
        await update.message.reply_text(f"Something went wrong: {exc}")
        return

    # Send prose reply
    if response["text"]:
        # Telegram has a 4096-char limit per message
        for chunk in _split(response["text"], 4000):
            await update.message.reply_text(chunk)

    # Send code in a separate preformatted block
    if response["code"]:
        for chunk in _split(response["code"], 3800):
            await update.message.reply_text(f"```\n{chunk}\n```", parse_mode="Markdown")


def _split(text: str, limit: int) -> list[str]:
    """Split long text into chunks under limit characters."""
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        parts.append(text[:limit])
        text = text[limit:]
    return parts


# ── Entry point ───────────────────────────────────────────────────────────────
def run_bot():
    token = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM")

    if not token:
        logger.error("TELEGRAM_TOKEN is not set.")
        sys.exit(1)

    logger.info("Starting Mika Telegram bot...")

    app = (
        ApplicationBuilder()
        .token(token)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("indexes", cmd_indexes))
    app.add_handler(CommandHandler("index", cmd_index))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__ == "__main__":
    run_bot()
