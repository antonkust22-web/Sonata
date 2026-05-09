import asyncio
import logging
import sqlite3
import requests  # Эта библиотека у вас точно есть
from urllib.parse import quote
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
    BASE_PATH = "/XWYB6HCgL7NBchJqxo" 
    URL = "https://78.17.1.43:10096"
    email = f"user_{user_id}"
    
    try:
        with requests.Session() as session:
            session.verify = False
            # 1. Логин
            login_url = f"{URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10)
            
            # 2. Проверяем, есть ли уже такой клиент
            get_url = f"{URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            inbound_data = session.get(get_url, timeout=10).json()
            
            if not inbound_data.get("success"):
                return "❌ Ошибка: Не найден Inbound ID 1"

            # Ищем клиента в списке настроек
            import json
            settings = json.loads(inbound_data["obj"]["settings"])
            clients = settings.get("clients", [])
            
            client_uuid = None
            for c in clients:
                if c.get("email") == email:
                    client_uuid = c.get("id")
                    break
            
            # 3. Если клиента нет — создаем его
            if not client_uuid:
                import uuid
                client_uuid = str(uuid.uuid4())
                add_url = f"{URL}{BASE_PATH}/panel/api/inbounds/addClient"
                client_data = {
                    "id": INBOUND_ID,
                    "settings": json.dumps({
                        "clients": [{
                            "id": client_uuid,
                            "email": email,
                            "limitIp": 2,
                            "totalGB": 0,
                            "expiryTime": 0,
                            "enable": True,
                            "tgId": user_id,
                            "subId": ""
                        }]
                    })
                }
                session.post(add_url, data=client_data, timeout=10)

            
                        # --- ШАГ 4: ФОРМИРОВАНИЕ ССЫЛКИ ---
            my_ip = "78.17.1.43"
            my_port = inbound_data["obj"]["port"]
            pbk = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38"
            sid = "32b6a4ff54ef1812"
            sni = "www.sony.com"
            
            # --- ИЗМЕНЕНИЯ ТУТ ---
            country_flag = "🇫🇮" # Поставь нужный флаг (например, 🇩🇪, 🇺🇸, 🇰🇿)
            country_name = "Финляндия" # Название страны
            server_type = "Premium" # Доп. описание (будет под заголовком)
            
            # Формируем красивый Remark (имя в списке)
            # Мы используем формат #Флаг Название?Описание
            remark_encoded = f"{country_flag} {country_name}?{server_type}"

            # Собираем ссылку. В конце ссылки вместо &remark={remark} ставим #{remark}
            config_link = (
                f"vless://{client_uuid}@{my_ip}:{my_port}"
                f"?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F"
                f"#{remark_encoded}"
            )
            # ----------------------
            
            return f"✅ Ключ готов!\n\n<code>{config_link}</code>"
                
    except Exception as e:
        return f"❌ Ошибка API: {str(e)[:50]}"




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



