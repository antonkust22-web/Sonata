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

# Текст в главном меню
text1 = (
    "<b>Обходите блокировки легко!</b>\n"
    "✅ Невидим для DPI\n"
    "✅ Работает в строгих сетях\n"
    "✅ Подключение в один клик\n\n"
    "Ваша подписка активна!"
)

# Инициализация
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- База данных ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
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
            # 1. Логин
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10)
            
            # 2. Получение данных
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            inbound_data = session.get(get_url, timeout=10).json()
            
            if not inbound_data.get("success"):
                return None, "❌ Ошибка: Не найден Inbound ID"

            settings = json.loads(inbound_data["obj"]["settings"])
            clients = settings.get("clients", [])
            
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)
            
            # 3. Создание клиента, если нет
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
            
            remark = quote("🇫🇮 Финляндия?Premium")
            config_link = (
                f"vless://{client_uuid}@{my_ip}:{my_port}"
                f"?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F"
                f"#{remark}"
            )
            
            happ_link = f"happ://import/{config_link}"
            return config_link, happ_link
                
    except Exception as e:
        return None, str(e)

# --- Клавиатуры ---
def get_welcome_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать работу", callback_data="main_menu")]
    ])

def get_inline_keyboard(happ_url="#"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ)", url=happ_url)],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="like")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="saling")],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="dislike")],
    ])

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(
        "👋 Привет! Я помогу тебе настроить быстрый VPN.\nНажми кнопку ниже:",
        reply_markup=get_welcome_keyboard()
    )

@dp.callback_query(F.data == "main_menu")
async def show_main_menu(callback: types.CallbackQuery):
    _, happ_url = get_vpn_config_manual(callback.from_user.id)
    await callback.message.answer(text1, parse_mode="HTML", reply_markup=get_inline_keyboard(happ_url))
    await callback.message.delete()

@dp.callback_query(F.data == "like")
async def kabinet(callback: types.CallbackQuery):
    await callback.answer("Загрузка...")
    vless, _ = get_vpn_config_manual(callback.from_user.id)
    
    text = (
        f"<b>👤 Личный кабинет</b>\n\n"
        f"<b>Ваш ID:</b> <code>{callback.from_user.id}</code>\n\n"
        f"<b>Ваша ссылка для Happ/Hiddify:</b>\n"
        f"<code>{vless}</code>\n\n"
        f"<i>Нажмите на текст выше, чтобы скопировать.</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.message.delete()

@dp.callback_query(F.data == "saling")
async def subscription(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]])
    await callback.message.answer("💎 <b>Тарифы:</b>\n\n1 месяц — 150₽\n3 месяца — 400₽", parse_mode="HTML", reply_markup=kb)
    await callback.message.delete()

@dp.callback_query(F.data == "dislike")
async def info(callback: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]])
    await callback.message.answer("Наш VPN работает на протоколе VLESS Reality. Это самый современный способ обхода блокировок.", reply_markup=kb)
    await callback.message.delete()

async def main():
    init_db()
    requests.packages.urllib3.disable_warnings()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())





