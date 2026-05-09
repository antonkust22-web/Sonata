import asyncio
import logging
import sqlite3
import requests
import json
import uuid
from urllib.parse import quote
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# --- НАСТРОЙКИ ПАНЕЛИ И БОТА ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
PANEL_URL = "https://78.17.1.43:10096"
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
BASE_PATH = "/XWYB6HCgL7NBchJqxo" 
INBOUND_ID = 1

# --- НАСТРОЙКИ СЕРВЕРА ---
COUNTRY_FLAG = "🇫🇮"            # Флаг сервера
COUNTRY_NAME = "Финляндия"       # Страна
SERVER_DESC = "VLESS Reality"  # Описание протокола

# Текст главного меню
text_main = (
    "<b>Обходите блокировки легко!</b>\n"
    "✅ Невидим для DPI\n"
    "✅ Работает в один клик\n\n"
    "Ваша подписка активна!"
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
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

# --- ЛОГИКА VPN ---
def get_vpn_config_manual(user_id):
    email = f"user_{user_id}"
    try:
        with requests.Session() as session:
            session.verify = False
            # 1. Авторизация
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10)
            
            # 2. Получение данных
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            inbound_data = session.get(get_url, timeout=10).json()
            
            if not inbound_data.get("success"):
                return None, "Ошибка API"

            settings = json.loads(inbound_data["obj"]["settings"])
            clients = settings.get("clients", [])
            
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)
            
            # 3. Создание клиента, если его нет
            if not client_uuid:
                client_uuid = str(uuid.uuid4())
                add_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient"
                client_data = {"id": INBOUND_ID, "settings": json.dumps({"clients": [{
                    "id": client_uuid, "email": email, "limitIp": 2, "totalGB": 0, "expiryTime": 0, "enable": True, "tgId": user_id, "subId": ""
                }]})}
                session.post(add_url, data=client_data, timeout=10)

            # 4. Формирование ссылки
            my_ip = "78.17.1.43"
            my_port = inbound_data["obj"]["port"]
            pbk = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38"
            sid = "32b6a4ff54ef1812"
            sni = "www.sony.com"
            
            remark_text = f"{COUNTRY_FLAG} {COUNTRY_NAME}?{SERVER_DESC}"
            remark_encoded = quote(remark_text)

            vless_link = (
                f"vless://{client_uuid}@{my_ip}:{my_port}"
                f"?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F"
                f"#{remark_encoded}"
            )
            
            happ_link = f"happ://import/{vless_link}"
            
            return vless_link, happ_link
                
    except Exception as e:
        return None, str(e)

# --- КЛАВИАТУРЫ ---
def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="📖 Инструкция", url="https://google.com")]
    ])

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(
        text_main,
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer("Генерация данных...")
    user_id = callback.from_user.id
    vless, happ = get_vpn_config_manual(user_id)
    
    if not vless:
        await callback.message.answer(f"❌ Ошибка: {happ}")
        return

    text = (
        f"<b>👤 Личный кабинет</b>\n\n"
        f"<b>Ваш ID:</b> <code>{user_id}</code>\n"
        f"<b>Статус:</b> Активен ✅\n\n"
        f"Ваш ключ (нажмите для копирования):\n"
        f"<code>{vless}</code>\n\n"
        f"Используйте кнопку ниже для быстрого импорта в Happ!"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Подключиться в Happ", url=happ)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]
    ])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "to_main")
async def to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text_main,
        parse_mode="HTML",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "buy")
async def buy(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💎 <b>Тарифы:</b>\n\n1 месяц — 150₽\n3 месяца — 400₽", 
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]])
    )

async def main():
    init_db()
    requests.packages.urllib3.disable_warnings() 
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())




