
'''
Interface for the project I decided to server everything through a telegram bot
'''

from telegram import Update

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from main import Main

import os

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("Hello world")

sessions = {}  # keep this at the top of your bot.py

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text

    if user_id not in sessions:
        sessions[user_id] = Main(user_id=user_id)
    main = sessions[user_id]

    response = main.query(text)  # now returns {"text": ..., "code": ...}

    # Send explanation first
    if response["text"]:
        await update.message.reply_text(response["text"])

    # Send code separately in preformatted block
    if response["code"]:
        await update.message.reply_text(f'```{response["code"]}```', parse_mode="Markdown")


if __name__ == "__main__":


    print("Telegram bot running....")

    key = os.getenv("TELEGRAM")

    app = ApplicationBuilder().token(key).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

