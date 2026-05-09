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

# --- Настройки ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
PANEL_URL = "https://78.17.1.43:10096"
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
INBOUND_ID = 1
BASE_PATH = "/XWYB6HCgL7NBchJqxo"

text1 = (
    "<b>Обходите блокировки легко!</b>\n"
    "✅ Невидим для DPI\n"
    "✅ Работает в строгих сетях\n"
    "✅ Подключение в один клик\n\n"
    "Ваша подписка активна!"
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- База данных ---
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

# --- Логика VPN (Мясо) ---
def get_vpn_config_manual(user_id):
    email = f"user_{user_id}"
    try:
        with requests.Session() as session:
            session.verify = False
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=5)
            
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            response = session.get(get_url, timeout=5).json()
            
            if not response.get("success"): return None, None

            settings = json.loads(response["obj"]["settings"])
            clients = settings.get("clients", [])
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)
            
            if not client_uuid:
                client_uuid = str(uuid.uuid4())
                add_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient"
                client_data = {"id": INBOUND_ID, "settings": json.dumps({"clients": [{
                    "id": client_uuid, "email": email, "limitIp": 2, "totalGB": 0, "expiryTime": 0, "enable": True, "tgId": user_id, "subId": ""
                }]})}
                session.post(add_url, data=client_data, timeout=5)

            my_ip = "78.17.1.43"
            my_port = response["obj"]["port"]
            pbk = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38"
            sid = "32b6a4ff54ef1812"
            sni = "://sony.com"
            remark = quote("🇫🇮 Finland Premium")
            
            link = f"vless://{client_uuid}@{my_ip}:{my_port}?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F#{remark}"
            return link, f"happ://import/{link}"
    except Exception:
        return None, None

# --- Клавиатура ---
def get_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ)", callback_data="connect_happ")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="info")],
    ])

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(text1, parse_mode="HTML", reply_markup=get_main_kb())

@dp.callback_query(F.data == "connect_happ")
async def connect(callback: types.CallbackQuery):
    await callback.answer("Генерирую ссылку...")
    loop = asyncio.get_event_loop()
    _, happ_url = await loop.run_in_executor(None, get_vpn_config_manual, callback.from_user.id)
    
    if happ_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
        await callback.message.edit_text("Ваша ссылка готова! Нажмите кнопку ниже для импорта:", reply_markup=kb)
    else:
        await callback.answer("❌ Ошибка связи с сервером", show_alert=True)

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    await callback.answer()
    loop = asyncio.get_event_loop()
    vless, _ = await loop.run_in_executor(None, get_vpn_config_manual, callback.from_user.id)
    
    text = f"<b>👤 Профиль</b>\nID: <code>{callback.from_user.id}</code>\n\nКлюч:\n<code>{vless if vless else 'Ошибка'}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(text1, parse_mode="HTML", reply_markup=get_main_kb())

@dp.callback_query(F.data == "buy")
async def buy(callback: types.CallbackQuery):
    await callback.answer("Раздел в разработке")

@dp.callback_query(F.data == "info")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("Наш VPN работает на протоколе VLESS Reality.", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]]))

async def main():
    init_db()
    requests.packages.urllib3.disable_warnings()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
