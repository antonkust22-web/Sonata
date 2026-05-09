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

# --- НАСТРОЙКИ ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
PANEL_URL = "https://78.17.1.43:10096"
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
BASE_PATH = "/XWYB6HCgL7NBchJqxo" 
INBOUND_ID = 1

# Настройки отображения в приложении
COUNTRY_FLAG = "🇫🇮"
COUNTRY_NAME = "Finland"
SERVER_DESC = "VLESS Reality"

# Текст меню
text_main = (
    "<b>Обходите блокировки легко!</b>\n"
    "✅ Невидим для DPI\n"
    "✅ Работает в строгих сетях\n"
    "✅ Подключение в один клик\n\n"
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
            # 1. Авторизация в панели
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10)
            
            # 2. Получение данных инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            response = session.get(get_url, timeout=10).json()
            
            if not response.get("success"):
                return None, "Ошибка API"

            settings = json.loads(response["obj"]["settings"])
            clients = settings.get("clients", [])
            
            # Ищем существующий UUID или создаем новый
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)
            
            if not client_uuid:
                client_uuid = str(uuid.uuid4())
                add_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient"
                client_data = {"id": INBOUND_ID, "settings": json.dumps({"clients": [{
                    "id": client_uuid, "email": email, "limitIp": 2, "totalGB": 0, "expiryTime": 0, "enable": True, "tgId": user_id, "subId": ""
                }]})}
                session.post(add_url, data=client_data, timeout=10)

            # 3. Сборка ссылки
            my_ip = "78.17.1.43"
            my_port = response["obj"]["port"]
            pbk = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38"
            sid = "32b6a4ff54ef1812"
            sni = "www.sony.com"
            
            remark = quote(f"{COUNTRY_FLAG} {COUNTRY_NAME}?{SERVER_DESC}")

            vless_link = (
                f"vless://{client_uuid}@{my_ip}:{my_port}"
                f"?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F"
                f"#{remark}"
            )
            
            # Ссылка для автоматического открытия в Happ
            happ_link = f"happ://import/{vless_link}"
            
            return vless_link, happ_link
                
    except Exception as e:
        return None, str(e)

# --- КЛАВИАТУРЫ ---
def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="📲 Инструкция", url="https://google.com")],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="about")]
    ])

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(text_main, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer("Генерация данных...")
    user_id = callback.from_user.id
    vless, happ = get_vpn_config_manual(user_id)
    
    if not vless:
        await callback.message.answer(f"❌ Ошибка подключения к серверу: {happ}")
        return

    text = (
        f"<b>👤 Личный кабинет</b>\n\n"
        f"<b>Ваш ID:</b> <code>{user_id}</code>\n"
        f"<b>Статус:</b> Активен ✅\n\n"
        f"Ваша ссылка:\n<code>{vless}</code>\n\n"
        f"Нажмите кнопку ниже, чтобы импортировать настройки в Happ автоматически!"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Подключиться в Happ", url=happ)],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery):
    await callback.message.edit_text(text_main, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "buy")
async def buy(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💎 <b>Доступные тарифы:</b>\n\n1 месяц — 150₽\n3 месяца — 400₽", 
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]])
    )

@dp.callback_query(F.data == "about")
async def about(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Наш VPN использует протокол VLESS Reality. Это обеспечивает максимальную скорость и защиту от блокировок.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]])
    )

async def main():
    init_db()
    requests.packages.urllib3.disable_warnings() 
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())




