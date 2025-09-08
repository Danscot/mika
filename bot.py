
'''
Interface for the project I decided to server everything through a telegram bot
'''

from telegram import Update

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from main import Main

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("Hello world")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = str(update.message.from_user.id)

    text = update.message.text

    # Get or create Mika session for 

    # Query Mika
    answer = session.query(text)

    await update.message.reply_text(answer)

if __name__ == "__main__":

    app = ApplicationBuilder().token("8398340834:AAHdL0e76S86St0rl3R8jXCnqdWA5s_LNps").build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

    print("Telegram bot running")
