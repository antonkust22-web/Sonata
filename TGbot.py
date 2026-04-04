import asyncio
import logging
import aiomysql  # Используем асинхронный драйвер
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

# --- Настройки ---
# ВАЖНО: Никогда не выкладывайте токен в открытый доступ! 
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"
text1 = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает в строгих сетях\n✅ Подключение в один клик\n\nДальше здесь будет информация о подписке"

db_config = {
    'host': '127.0.0.1',
    'user': 'Kadin',
    'password': '542013',
    'db': 'Sonata',  # В aiomysql параметр называется 'db', а не 'database'
    'autocommit': True
}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Асинхронная работа с базой данных MySQL ---

async def init_db():
    """Создание таблицы при запуске"""
    try:
        conn = await aiomysql.connect(**db_config)
        async with conn.cursor() as cur:
            await cur.execute('CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY)')
        conn.close()
        logging.info("База данных MySQL инициализирована.")
    except Exception as e:
        logging.error(f"Ошибка при инициализации БД: {e}")

async def user_exists(user_id):
    """Асинхронная проверка наличия пользователя"""
    conn = await aiomysql.connect(**db_config)
    async with conn.cursor() as cur:
        await cur.execute('SELECT 1 FROM users WHERE user_id = %s', (user_id,))
        result = await cur.fetchone()
    conn.close()
    return result is not None

async def add_user(user_id):
    """Асинхронное добавление пользователя"""
    try:
        conn = await aiomysql.connect(**db_config)
        async with conn.cursor() as cur:
            await cur.execute('INSERT IGNORE INTO users (user_id) VALUES (%s)', (user_id,))
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка add_user: {e}")

# --- Клавиатуры (без изменений) ---
def get_welcome_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Перейти в главное меню", callback_data="main_menu")]
    ])

def get_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подключить устройство", url="https://google.com")],
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

# --- Хендлеры (теперь вызывают await для БД) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Теперь вызываем функции БД с await
    if not await user_exists(message.from_user.id):
        await add_user(message.from_user.id)
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
    await callback.answer()
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name
    username = f"@{callback.from_user.username}" if callback.from_user.username else "не установлен"

    text = (
        f"<b>👤 Личный кабинет</b>\n\n"
        f"<b>Имя:</b> {first_name}\n"
        f"<b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"<b>Username:</b> {username}\n\n"
        f"Здесь информация о вашей активности"
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
    await init_db() # Инициализация теперь тоже асинхронная
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
