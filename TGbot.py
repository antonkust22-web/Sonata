import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from py3xui import ApiClient, Client

# --- Настройки (ЗАМЕНИТЕ НА СВОИ) ---
API_TOKEN = 'ВАШ_НОВЫЙ_ТОКЕН_ИЗ_BOTFATHER'
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"

# Для PANEL_URL используйте только протокол, IP и порт
PANEL_URL = "http://78.17.1.43:10096" 
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
INBOUND_ID = 1  # Убедитесь, что в панели ID именно 1

# Сообщение в главном меню
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
xui_api = ApiClient(PANEL_URL, PANEL_USER, PANEL_PASSWORD)

# --- База данных ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    conn.commit()
    conn.close()

def user_exists(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone()
    conn.close()
    return exists

def add_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

# --- Логика 3x-ui ---
async def get_vpn_config(user_id):
    try:
        await xui_api.login()
        email = f"user_{user_id}"
        
        # Получаем данные подключения
        inbound = await xui_api.inbound.get_by_id(INBOUND_ID)
        if not inbound:
            return "Ошибка: Подключение (Inbound) не найдено в панели."
        
        # Ищем клиента
        client_exists = any(c.email == email for c in inbound.settings.clients)
        
        if not client_exists:
            # Создаем нового клиента (UUID сгенерируется автоматически)
            new_client = Client(email=email, enable=True, inbound_id=INBOUND_ID)
            await xui_api.client.add(INBOUND_ID, [new_client])
            logging.info(f"Создан новый клиент для {user_id}")

        # Получаем ссылки (подписки)
        configs = await xui_api.client.get_config(INBOUND_ID)
        for cfg in configs:
            if email in cfg:
                return cfg
        
        return "Ключ создан. Скопируйте его в приложении Happ."
    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        return "Сервер временно недоступен. Попробуйте позже."

# --- Клавиатуры ---
def get_welcome_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать работу", callback_data="main_menu")]
    ])

def get_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Инструкция (Happ/Hiddify)", url="https://google.com")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="like")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="saling")],
        [InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="dislike")],
    ])

def get_back_button():
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")]

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not user_exists(message.from_user.id):
        add_user(message.from_user.id)
        await message.answer(
            "👋 Привет! Я помогу тебе настроить быстрый VPN.\nНажми кнопку ниже:",
            reply_markup=get_welcome_keyboard()
        )
    else:
        await send_main_menu(message)

async def send_main_menu(message: types.Message):
    try:
        await message.answer_video(
            video=VIDEO_ID,
            caption=text1,
            parse_mode="HTML",
            reply_markup=get_inline_keyboard()
        )
    except Exception:
        await message.answer(text1, parse_mode="HTML", reply_markup=get_inline_keyboard())

@dp.callback_query(F.data == "main_menu")
async def show_main_menu(callback: types.CallbackQuery):
    await send_main_menu(callback.message)
    await callback.message.delete()

@dp.callback_query(F.data == "like")
async def kabinet(callback: types.CallbackQuery):
    await callback.answer("Запрашиваю ключ...")
    
    vpn_config = await get_vpn_config(callback.from_user.id)
    
    text = (
        f"<b>👤 Личный кабинет</b>\n\n"
        f"<b>Ваш ID:</b> <code>{callback.from_user.id}</code>\n\n"
        f"<b>Ваша ссылка для Happ/Hiddify:</b>\n"
        f"<code>{vpn_config}</code>\n\n"
        f"<i>Нажмите на текст выше, чтобы скопировать.</i>"
    )

    await callback.message.answer(
        text, 
        parse_mode="HTML", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_back_button()])
    )
    await callback.message.delete()

@dp.callback_query(F.data == "saling")
async def subscription(callback: types.CallbackQuery):
    await callback.message.answer(
        "💎 <b>Тарифы:</b>\n\n1 месяц — 150₽\n3 месяца — 400₽", 
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_back_button()])
    )
    await callback.message.delete()

@dp.callback_query(F.data == "dislike")
async def info(callback: types.CallbackQuery):
    await callback.message.answer(
        "Наш VPN работает на протоколе VLESS Reality. Это самый современный способ обхода блокировок.", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_back_button()])
    )
    await callback.message.delete()

async def main():
    init_db()
    try:
        await xui_api.login()
        print("✅ Подключение к 3x-ui успешно!")
    except Exception as e:
        print(f"❌ Ошибка подключения к панели: {e}")
        
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

