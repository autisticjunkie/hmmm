import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f'Hello {user.first_name}! I am working!')

def main():
    token = "7790381038:AAE26s1oHYvlZX2wyY_cW7VsjJmNaxXFlYc"
    
    # Create application
    application = Application.builder().token(token).build()

    # Add handler
    application.add_handler(CommandHandler("start", start))

    # Start the bot
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
