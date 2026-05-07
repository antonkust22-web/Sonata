import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from py3xui import ApiClient, Client

# --- Настройки ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"
text1 = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает в строгих сетях\n✅ Подключение в один клик\n\nДальше здесь будет информация о подписке"

# --- Настройки 3x-ui (ЗАПОЛНИТЕ СВОИМИ ДАННЫМИ) ---
PANEL_URL = "https://78.17.1.43:10096" 
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
INBOUND_ID = 1  # ID вашего подключения в панели (обычно 1)

# Инициализация бота и API панели
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
xui_api = ApiClient(PANEL_URL, PANEL_USER, PANEL_PASSWORD)

# --- Работа с базой данных ---
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

# --- Работа с 3x-ui ---
async def get_vpn_config(user_id):
    """Создает клиента в панели, если его нет, и возвращает ссылку"""
    try:
        await xui_api.login()
        email = f"user_{user_id}"
        
        # Получаем данные входящего подключения
        inbound = await xui_api.inbound.get_by_id(INBOUND_ID)
        
        # Проверяем, существует ли клиент
        client_exists = False
        for client in inbound.settings.clients:
            if client.email == email:
                client_exists = True
                break
        
        # Если клиента нет — создаем
        if not client_exists:
            new_client = Client(email=email, enable=True, inbound_id=INBOUND_ID)
            await xui_api.client.add(INBOUND_ID, [new_client])
            # Обновляем данные после добавления
            inbound = await xui_api.inbound.get_by_id(INBOUND_ID)

        # Генерация ссылки (для VLESS/VMess/Trojan)
        # Примечание: py3xui возвращает список ссылок для инбаунда
        client_configs = await xui_api.client.get_config(INBOUND_ID)
        for cfg in client_configs:
            if email in cfg:
                return cfg
        
        return "Ключ создан, но ссылку не удалось получить автоматически."
    except Exception as e:
        logging.error(f"Ошибка API панели: {e}")
        return "Ошибка подключения к серверу VPN."

# --- Клавиатуры ---
def get_welcome_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Перейти в главное меню", callback_data="main_menu")]
    ])

def get_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подключить устройство", url="https://google.com")], # Замените на свою инструкцию
        [InlineKeyboardButton(text="🏡 Личный кабинет", callback_data="like")],
        [InlineKeyboardButton(text="👑 Оформление подписки", callback_data="saling")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="dislike")],
    ])

def get_back_button():
    return [InlineKeyboardButton(text="⬅️ На главную", callback_data="main_menu")]

# --- Вспомогательные функции ---
async def send_main_menu(message: types.Message):
    try:
        await message.answer_video(
            video=VIDEO_ID,
            caption=text1,
            parse_mode="HTML",
            reply_markup=get_inline_keyboard()
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке видео: {e}")
        await message.answer(text1, parse_mode="HTML", reply_markup=get_inline_keyboard())

# --- Хендлеры ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not user_exists(message.from_user.id):
        add_user(message.from_user.id)
        await message.answer(
            "👋 Привет! Добро пожаловать в наш VPN-сервис.\nНажмите кнопку ниже, чтобы начать.",
            reply_markup=get_welcome_keyboard()
        )
    else:
        await send_main_menu(message)

@dp.callback_query(F.data == "main_menu")
async def show_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    await send_main_menu(callback.message)
    await callback.message.delete()

@dp.callback_query(F.data == "like")
async def kabinet(callback: types.CallbackQuery):
    await callback.answer("Загружаем данные...")
    
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name
    
    # Получаем ключ из панели 3x-ui
    vpn_config = await get_vpn_config(user_id)

    text = (
        f"<b>👤 Личный кабинет</b>\n\n"
        f"<b>Имя:</b> {first_name}\n"
        f"<b>ID:</b> <code>{user_id}</code>\n\n"
        f"<b>Ваш ключ доступа:</b>\n"
        f"<code>{vpn_config}</code>\n\n"
        f"<i>Нажмите на ключ, чтобы скопировать его.</i>"
    )

    await callback.message.answer(
        text, 
        parse_mode="HTML", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_back_button()])
    )
    await callback.message.delete()

@dp.callback_query(F.data == "dislike")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "Здесь информация о нашем VPN", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_back_button()])
    )
    await callback.message.delete()

@dp.callback_query(F.data == "saling")
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

async def main():
    logging.info("Запуск бота...")
    init_db()
    # Проверка соединения с панелью
    try:
        await xui_api.login()
        logging.info("Связь с 3x-ui установлена!")
    except Exception as e:
        logging.error(f"Ошибка связи с 3x-ui: {e}")
        
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
