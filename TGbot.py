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

text1 = "👋<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает в строгих сетях\n✅ Подключение в один клик\n\nДальше здесь будет информация о подписке"


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


from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Вставьте сюда ваш проверенный File ID, который заработал! ---
VIDEO_MAIN = "BAACAgIAAxkBAAMLagtRYohK4W-WOfghGVIlBtWuyIoAAjWeAAL-Q1lIcZMozT4F8hw7BA"

# --- Клавиатуры ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ) РАЗРАБОТКА", callback_data="connect")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="📖 Информация и поддержка", callback_data="info")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    add_user(message.from_user.id)
    # Отправляем главное видео вместе с текстом text1
    await message.answer_video(
        video=VIDEO_MAIN,
        caption=text1,
        reply_markup=main_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer()
    config, _ = get_vpn_config_manual(callback.from_user.id)
    if config:
        text = f"<b>👤 Личный кабинет</b>\n\n<b>Ваш ID:</b> <code>{callback.from_user.id}</code>\n\n<b>Ваш ключ:</b>\n<code>{config}</code>"
    else:
        text = "❌ Не удалось получить ключ. Проверьте настройки панели."
        
    # ИСПРАВЛЕНО: Меняем ТОЛЬКО текст (caption) под вашим стартовым видео
    await callback.message.edit_caption(caption=text, reply_markup=back_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer()
    _, happ_url = get_vpn_config_manual(callback.from_user.id)
    if happ_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
        # ИСПРАВЛЕНО: Меняем только текст под видео
        await callback.message.edit_caption(caption="Нажмите кнопку ниже для импорта в Happ:", reply_markup=kb)
    else:
        await callback.answer("❌ Ошибка сервера", show_alert=True)

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.answer()
    # ИСПРАВЛЕНО: Возвращаем под видео первоначальный текст text1
    await callback.message.edit_caption(caption=text1, reply_markup=main_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "info")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        "Новый VPN будет обеспечивать высокую скорость соединения и улучшенную конфиденциальность пользователей. "
        "Планируется внедрение современных протоколов безопасности и удобный интерфейс.\n\n"
        "Тех.поддержка @Sonata_VPN_Admin"
    )
    # ИСПРАВЛЕНО: Меняем только текст под видео
    await callback.message.edit_caption(caption=text, reply_markup=back_kb())

@dp.callback_query(F.data == "buy")
async def subscription(callback: types.CallbackQuery):
    await callback.answer()
    buy_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цена и время", url="https://google.com")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])
    # ИСПРАВЛЕНО: Меняем только текст под видео
    await callback.message.edit_caption(caption="Здесь будут условия и цены", reply_markup=buy_kb)



# --- Запуск ---
async def main():
    init_db()
    requests.packages.urllib3.disable_warnings()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
