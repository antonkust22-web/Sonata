import asyncio
import logging
import aiomysql
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"
text1 = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает в строгих сетях\n\nДальше здесь будет информация о подписке"

db_config = {
    'host': '127.0.0.1',
    'user': 'Kadin',
    'password': '542013',
    'db': 'Sonata',
    'autocommit': True
}

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
db_pool = None  # Переменная для хранения пула

async def init_db():
    """Создание пула и таблицы"""
    global db_pool
    try:
        db_pool = await aiomysql.create_pool(**db_config, minsize=1, maxsize=10)
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute('CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY)')
        logging.info("База данных и пул инициализированы.")
    except Exception as e:
        logging.error(f"КРИТИЧЕСКАЯ ОШИБКА БД: {e}")

async def user_exists(user_id):
    if db_pool is None: return False
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute('SELECT 1 FROM users WHERE user_id = %s', (user_id,))
            result = await cur.fetchone()
            return result is not None

async def add_user(user_id):
    if db_pool is None: return
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute('INSERT IGNORE INTO users (user_id) VALUES (%s)', (user_id,))
    except Exception as e:
        logging.error(f"Ошибка add_user: {e}")

# --- Клавиатуры ---
def get_welcome_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Меню", callback_data="main_menu")]])

def get_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏡 Личный кабинет", callback_data="like")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="dislike")],
    ])

def get_back_button():
    return [InlineKeyboardButton(text="⬅️ На главную", callback_data="main_menu")]

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Добавляем await и проверку
    exists = await user_exists(message.from_user.id)
    if not exists:
        await add_user(message.from_user.id)
        await message.answer("👋 Привет! Нажмите кнопку ниже.", reply_markup=get_welcome_keyboard())
    else:
        await message.answer_video(video=VIDEO_ID, caption=text1, parse_mode="HTML", reply_markup=get_inline_keyboard())

@dp.callback_query(F.data == "main_menu")
async def show_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer_video(video=VIDEO_ID, caption=text1, parse_mode="HTML", reply_markup=get_inline_keyboard())
    await callback.message.delete()

@dp.callback_query(F.data == "like")
async def kabinet(callback: types.CallbackQuery):
    await callback.answer()
    text = f"<b>👤 Кабинет</b>\nID: <code>{callback.from_user.id}</code>"
    await callback.message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_back_button()]))
    await callback.message.delete()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
