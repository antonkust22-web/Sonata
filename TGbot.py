import asyncio
import logging
import aiohttp
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


# --- ЛОГИКА VPN (Асинхронная) ---
async def get_vpn_config(user_id):
    email = f"user_{user_id}"
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
        try:
            # 1. Логин
            await session.post(f"{PANEL_URL}{BASE_PATH}/login", 
                               data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=5)
            
            # 2. Получение данных
            async with session.get(f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}", timeout=5) as resp:
                response = await resp.json()
            
            if not response.get("success"): return None, None

            settings = json.loads(response["obj"]["settings"])
            clients = settings.get("clients", [])
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)
            
            # 3. Создание клиента, если нет
            if not client_uuid:
                client_uuid = str(uuid.uuid4())
                client_data = {"id": INBOUND_ID, "settings": json.dumps({"clients": [{
                    "id": client_uuid, "email": email, "limitIp": 2, "totalGB": 0, "expiryTime": 0, "enable": True, "tgId": user_id, "subId": ""
                }]})}
                await session.post(f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient", data=client_data)

            my_ip, my_port = "78.17.1.43", response["obj"]["port"]
            pbk, sid, sni = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38", "32b6a4ff54ef1812", "://sony.com"
            remark = quote("🇫🇮 Finland Premium")
            
            link = f"vless://{client_uuid}@{my_ip}:{my_port}?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F#{remark}"
            return link, f"happ://import/{link}"
        except Exception as e:
            logging.error(f"Ошибка VPN: {e}")
            return None, None

# --- КЛАВИАТУРЫ ---
def welcome_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать работу", callback_data="main_menu")]
    ])

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ)", callback_data="connect")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="profile")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="saling")],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="info")]
    ])
    
def get_back_button():
    return [InlineKeyboardButton(text="⬅️ На главную", callback_data="main_menu")]
    
# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Работает мгновенно, так как нет запроса к VPN
    await message.answer("👋 Привет! Я помогу тебе настроить быстрый VPN.\nНажми кнопку ниже, чтобы войти в меню:", 
                         reply_markup=welcome_kb())

@dp.callback_query(F.data == "main_menu")
@dp.callback_query(F.data == "back")
async def show_menu(callback: types.CallbackQuery):
    await callback.answer()
    text1
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=main_kb())
    
dp.callback_query(F.data == "saling")
async def subscription(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Здесь будут условия и цены", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Цена и время", url="https://google.com")],
            get_back_button()
        ])
    )
    await callback.message.delete()


@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer("⏳ Генерирую ссылку...")
    _, happ_url = await get_vpn_config(callback.from_user.id)
    
    if happ_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ ИМПОРТИРОВАТЬ В HAPP", url=happ_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
        await callback.message.edit_text("Ваша ссылка готова! Нажмите кнопку ниже для импорта:", reply_markup=kb)
    else:
        await callback.answer("❌ Ошибка связи с сервером", show_alert=True)

@dp.callback_query(F.data == "profile")
async def profile(callback: types.CallbackQuery):
    await callback.answer("⏳ Загрузка профиля...")
    vless, _ = await get_vpn_config(callback.from_user.id)
    
    text = f"<b>👤 Профиль</b>\nID: <code>{callback.from_user.id}</code>\n\nКлюч:\n<code>{vless or 'Ошибка'}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query(F.data == "info")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("Наш VPN работает на протоколе VLESS Reality.", 
                                     reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]]))

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
