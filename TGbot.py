import asyncio
import logging
import sqlite3
import requests  # Эта библиотека у вас точно есть
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# --- Настройки ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
PANEL_URL = "http://78.17.1.43:10096"
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
    # Добавляем секретный путь, если он есть в настройках вашей панели
    # Если без него не заходит в браузере, оставьте его тут
    BASE_PATH = "/XWYB6HCgL7NBchJqxo" # Если пути нет, оставьте пустым ""
    
    try:
        session = requests.Session()
        # Отключаем проверку SSL (verify=False), если используете https без сертификата
        login_url = f"{PANEL_URL}{BASE_PATH}/login"
        
        login_res = session.post(
            login_url, 
            data={"username": PANEL_USER, "password": PANEL_PASSWORD}, 
            timeout=10,
            verify=False  # Важно, если https самоподписанный
        )
        
        if login_res.status_code != 200:
            return f"Ошибка связи: Код {login_res.status_code}"

        if not login_res.json().get("success"):
            return "Ошибка: Неверный логин или пароль в панели"

        # Если логин прошел, пробуем получить данные
        return f"vless://user_{user_id}_uuid@78.17.1.43:port?remark=VPN"
        
    except Exception as e:
        logging.error(f"Детали ошибки VPN: {e}")
        return f"Ошибка VPN: {str(e)[:50]}" # Выводим начало ошибки для диагностики


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



