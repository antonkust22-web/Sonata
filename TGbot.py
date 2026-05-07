import asyncio
import logging
import sqlite3
import requests  # Эта библиотека у вас точно есть
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# --- Настройки ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
PANEL_URL = "https://78.17.1.43:10096"
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
    # ВАЖНО: Проверьте, совпадает ли этот путь с тем, что вы вводите в браузере!
    BASE_PATH = "/XWYB6HCgL7NBchJqxo" 
    
    # Убедитесь, что здесь правильный протокол (http или https)
    URL = "https://78.17.1.43:10096" 
    
    try:
        # Используем session, чтобы сохранить куки (cookie) авторизации
        with requests.Session() as session:
            # Отключаем все проверки SSL для теста
            session.verify = False
            
            login_url = f"{URL}{BASE_PATH}/login"
            payload = {"username": PANEL_USER, "password": PANEL_PASSWORD}
            
            # Делаем запрос на логин
            response = session.post(login_url, data=payload, timeout=15)
            
            # Если получили ответ, пробуем понять, что внутри
            if response.status_code == 200:
                try:
                    res_json = response.json()
                    if res_json.get("success"):
                        return f"✅ Доступ разрешен!\nВаш ID: {user_id}\nЗапрос к API прошел успешно."
                    else:
                        return "❌ Ошибка: Панель отклонила логин/пароль."
                except:
                    return "❌ Сервер прислал не JSON (проверьте BASE_PATH)"
            else:
                return f"❌ Ошибка: Сервер вернул код {response.status_code}"
                
    except requests.exceptions.ConnectionError:
        return "❌ Ошибка: Не удалось достучаться до IP (порт закрыт?)"
    except Exception as e:
        # Выводим только текст ошибки без лишних деталей
        err_msg = str(e)
        if "UnknownProtocol" in err_msg:
            return "❌ Ошибка: Проблемы с SSL/HTTPS (попробуйте сменить протокол в коде)"
        return f"❌ Ошибка: {err_msg[:40]}"



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



