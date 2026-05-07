import asyncio
import logging
import sqlite3
import requests  # Эта библиотека у вас точно есть
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# --- Настройки ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
PANEL_URL = "https://78.17.1.43:10096/XWYB6HCgL7NBchJqxo/"
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
INBOUND_ID = 1

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- База данных (упрощенно) ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

# --- Функция VPN (через прямые запросы) ---
def get_vpn_config_manual(user_id):
    """Работает без библиотеки py3xui"""
    try:
        session = requests.Session()
        # 1. Авторизация
        login_res = session.post(f"{PANEL_URL}/login", data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=5)
        if not login_res.json().get("success"):
            return "Ошибка входа в панель"

        # 2. Получение списка клиентов
        inbound_res = session.get(f"{PANEL_URL}/panel/api/inbounds/get/{INBOUND_ID}", timeout=5)
        # Если всё ок, здесь должна быть логика поиска/добавления
        # Для начала просто вернем текст, чтобы проверить, не упадет ли бот
        return f"vless://uuid-будет-тут@78.17.1.43:port?remark=user_{user_id}"
    except Exception as e:
        return f"Ошибка VPN: {e}"

# --- Клавиатуры ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="📖 Инфо", callback_data="info")]
    ])

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(
        "👋 Бот активирован! Выберите действие:",
        reply_markup=main_kb()
    )

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer()
    config = get_vpn_config_manual(callback.from_user.id)
    await callback.message.edit_text(
        f"<b>Личный кабинет</b>\n\nВаш ключ:\n<code>{config}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
    )

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("Выберите действие:", reply_markup=main_kb())

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())



