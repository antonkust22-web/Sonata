import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from aiogram.client.session.aiohttp import AiohttpSession

# Если у вас есть прокси (например, http://127.0.0.1:8080)
session = AiohttpSession(proxy="http://109.120.190.5:443")
bot = Bot(token="8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI", session=session)


# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен вашего бота (получите у @id199142634 (@BotFather))
TOKEN = "8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI"

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n"
        f"Я визуал-бот! Рад тебя видеть."
    )

# Обработчик команды /help (опционально)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Доступные команды:\n"
        "/start - Начать общение\n"
        "/help - Показать это сообщение"
    )

def main():
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Запускаем бота
    print("🤖 Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()

