import asyncio
import logging
import sqlite3
import requests
import json
import uuid
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# --- Настройки (ОБЯЗАТЕЛЬНО ОБНОВИТЕ ТОКЕН И ПАРОЛЬ) ---
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

# --- Исправленная функция VPN ---
def get_vpn_config_manual(user_id):
    email = f"user_{user_id}"
    try:
        with requests.Session() as session:
            session.verify = False
            # 1. Логин
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10)
            
            # 2. Получение данных инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            resp = session.get(get_url, timeout=10).json()
            
            if not resp.get("success"):
                return None, None

            settings = json.loads(resp["obj"]["settings"])
            clients = settings.get("clients", [])
            
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)
            
            # 3. Создание клиента, если его нет
            if not client_uuid:
                client_uuid = str(uuid.uuid4())
                add_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient"
                client_data = {
                    "id": INBOUND_ID,
                    "settings": json.dumps({
                        "clients": [{
                            "id": client_uuid, "email": email, "limitIp": 2, "totalGB": 0, 
                            "expiryTime": 0, "enable": True, "tgId": user_id, "subId": ""
                        }]
                    })
                }
                session.post(add_url, data=client_data, timeout=10)

            # 4. Формирование рабочей ссылки по вашему образцу
            my_ip = "78.17.1.43"
            my_port = resp["obj"]["port"]
            pbk = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38"
            sid = "32b6a4ff54ef1812"
            sni = "www.sony.com"
            
            country_flag = "🇫🇮"
            country_name = "Финляндия"
            server_type = "Premium"
            remark = f"{country_flag} {country_name}?{server_type}"

            config_link = (
                f"vless://{client_uuid}@{my_ip}:{my_port}"
                f"?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F"
                f"#{remark}"
            )
            
            # Возвращаем кортеж: (чистая ссылка, ссылка для Happ)
            return config_link, f"happ://import/{config_link}"
                
    except Exception as e:
        logging.error(f"Ошибка VPN: {e}")
        return None, None

# --- Клавиатуры ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ)", callback_data="connect")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="instruction")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]])

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    await message.answer("👋 <b>Добро пожаловать!</b>\nВыберите действие:", reply_markup=main_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer()
    config, _ = get_vpn_config_manual(callback.from_user.id)
    if config:
        text = f"<b>👤 Личный кабинет</b>\n\n<b>Ваш ID:</b> <code>{callback.from_user.id}</code>\n\n<b>Ваш ключ:</b>\n<code>{config}</code>"
    else:
        text = "❌ Не удалось получить ключ. Проверьте настройки панели."
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb())

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer("Генерирую...")
    _, happ_url = get_vpn_config_manual(callback.from_user.id)
    if happ_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
        await callback.message.edit_text("Нажмите кнопку ниже для импорта в Happ:", reply_markup=kb)
    else:
        await callback.answer("❌ Ошибка сервера", show_alert=True)

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.message.edit_text("👋 <b>Добро пожаловать!</b>", reply_markup=main_kb(), parse_mode="HTML")

# --- Запуск ---
async def main():
    init_db()
    requests.packages.urllib3.disable_warnings()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
