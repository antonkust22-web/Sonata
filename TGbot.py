import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command


# --- Настройки (ЗАМЕНИТЕ НА СВОИ) ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI' # Получите новый в @BotFather
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"

# Используем только IP и Порт (без лишних путей)
PANEL_URL = "http://78.17.1.43:10096" 
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
INBOUND_ID = 1

# Сообщения
text1 = "<b>Обходите блокировки легко!</b>\n✅ Работает в строгих сетях\n✅ Подключение в один клик"

# Настройка логирования (выводит ошибки в консоль)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
xui_api = ApiClient(PANEL_URL, PANEL_USER, PANEL_PASSWORD)

# --- База данных ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def user_exists(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone()
    conn.close()
    return exists

def add_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

# --- Логика VPN ---
async def get_vpn_config(user_id):
    try:
        await xui_api.login()
        email = f"user_{user_id}"
        inbound = await xui_api.inbound.get_by_id(INBOUND_ID)
        
        if not inbound:
            return "Ошибка: Inbound ID не найден в панели."

        client_exists = any(c.email == email for c in inbound.settings.clients)
        if not client_exists:
            new_client = Client(email=email, enable=True, inbound_id=INBOUND_ID)
            await xui_api.client.add(INBOUND_ID, [new_client])

        configs = await xui_api.client.get_config(INBOUND_ID)
        for cfg in configs:
            if email in cfg:
                return cfg
        return "Ключ готов, но ссылку получить не удалось."
    except Exception as e:
        logging.error(f"VPN API Error: {e}")
        return "Ошибка подключения к VPN-серверу."

# --- Клавиатуры ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="like")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="saling")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="dislike")]
    ])

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    logging.info(f"Команда /start от {message.from_user.id}")
    add_user(message.from_user.id)
    
    # Сначала пробуем отправить видео, если не выйдет — просто текст
    try:
        await message.answer_video(
            video=VIDEO_ID,
            caption=f"Привет, {message.from_user.first_name}!\n\n{text1}",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logging.warning(f"Не удалось отправить видео: {e}")
        await message.answer(
            f"Привет, {message.from_user.first_name}!\n\n{text1}",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

@dp.callback_query(F.data == "like")
async def show_cabinet(callback: types.CallbackQuery):
    await callback.answer("Загрузка...")
    config = await get_vpn_config(callback.from_user.id)
    
    await callback.message.answer(
        f"<b>👤 Личный кабинет</b>\n\nВаш ключ:\n<code>{config}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="back")]
        ])
    )
    await callback.message.delete()

@dp.callback_query(F.data == "back")
async def go_back(callback: types.CallbackQuery):
    await cmd_start(callback.message)
    await callback.message.delete()

@dp.callback_query(F.data == "saling")
async def show_shop(callback: types.CallbackQuery):
    await callback.message.answer("Здесь будут тарифы.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back")]
    ]))

async def main():
    init_db()
    logging.info("Бот запускается...")
    # Не блокируем работу бота проверкой панели, просто выводим статус
    try:
        await xui_api.login()
        logging.info("Связь с панелью 3x-ui установлена!")
    except Exception as e:
        logging.error(f"Панель 3x-ui недоступна: {e}")
        
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот выключен")


