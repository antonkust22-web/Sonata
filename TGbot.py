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
            # 1. Логин
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10)
            
            # 2. Получение данных
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            inbound_data = session.get(get_url, timeout=10).json()
            
            if not inbound_data.get("success"):
                return None, "❌ Ошибка API"

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
            my_ip, my_port = "78.17.1.43", inbound_data["obj"]["port"]
            pbk, sid, sni = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38", "32b6a4ff54ef1812", "www.sony.com"
            
            remark = quote("🇫🇮 Финляндия?Premium")
            link = f"vless://{client_uuid}@{my_ip}:{my_port}?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F#{remark}"
            
            return link, f"happ://import/{link}"
                
    except Exception as e:
        return None, str(e)

# --- Клавиатуры ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ)", callback_data="connect")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="instruction")],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="info")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(
        "👋 <b>Добро пожаловать!</b>\nВыберите нужное действие в меню ниже:",
        reply_markup=main_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer("⏳ Загрузка...")
    config, _ = get_vpn_config_manual(callback.from_user.id)
    text = (
        f"<b>👤 Личный кабинет</b>\n\n"
        f"<b>Ваш ID:</b> <code>{callback.from_user.id}</code>\n"
        f"<b>Ваш ключ:</b>\n<code>{config if config else 'Ошибка'}</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb())

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer("⏳ Генерирую ссылку...")
    _, happ_url = get_vpn_config_manual(callback.from_user.id)
    if happ_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
        await callback.message.edit_text("Нажмите кнопку ниже для быстрого импорта в приложение Happ:", reply_markup=kb)
    else:
        await callback.answer("❌ Ошибка соединения", show_alert=True)

@dp.callback_query(F.data == "buy")
async def buy(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("💳 <b>Пополнение баланса</b>\n\nТарифы:\n1 мес. — 150₽\n3 мес. — 400₽\n\nДля оплаты напишите администратору.", parse_mode="HTML", reply_markup=back_kb())

@dp.callback_query(F.data == "instruction")
async def instruction(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("📖 <b>Инструкция</b>\n\n1. Скачайте приложение Happ.\n2. Нажмите кнопку 'Подключиться' в боте.\n3. Импортируйте ключ и включите VPN.", parse_mode="HTML", reply_markup=back_kb())

@dp.callback_query(F.data == "info")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("ℹ️ <b>О сервисе</b>\n\nМы используем протокол VLESS Reality для максимальной скорости и безопасности.", parse_mode="HTML", reply_markup=back_kb())

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("👋 <b>Добро пожаловать!</b>\nВыберите нужное действие в меню ниже:", reply_markup=main_kb(), parse_mode="HTML")

async def main():
    init_db()
    requests.packages.urllib3.disable_warnings()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
