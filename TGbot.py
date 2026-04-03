import sqlite3
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"
text1 = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает в строгих сетях\n✅ Подключение в один клик\n\nДальше здесь будет информация о подписке"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Работа с БД (SQLite) ---
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
    return exists is not None

def add_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

# --- Клавиатуры ---
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

# --- Функции отображения меню (чтобы не дублировать код) ---
async def send_main_menu(message_or_callback, user_id):
    # Если это callback, отвечаем на него
    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.answer()
        msg = message_or_callback.message
    else:
        msg = message_or_callback

    try:
        await bot.send_video(
            chat_id=user_id,
            video=VIDEO_ID,
            caption=text1,
            parse_mode="HTML",
            reply_markup=get_inline_keyboard()
        )
        await msg.delete()
    except Exception as e:
        logging.error(f"Ошибка при отправке видео: {e}")
        await bot.send_message(
            chat_id=user_id,
            text=text1,
            parse_mode="HTML",
            reply_markup=get_inline_keyboard()
        )
        await msg.delete()

# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if user_exists(message.from_user.id):
        # Если пользователь уже есть в БД, сразу шлем главное меню
        await send_main_menu(message, message.from_user.id)
    else:
        # Если новый пользователь — сохраняем его и шлем приветствие
        add_user(message.from_user.id)
        await message.answer(
            "👋 Привет! Добро пожаловать в наш VPN-сервис.\nНажмите кнопку ниже, чтобы начать.",
            reply_markup=get_welcome_keyboard()
        )

@dp.callback_query(F.data == "main_menu")
async def show_main_menu_callback(callback: types.CallbackQuery):
    await send_main_menu(callback, callback.from_user.id)

@dp.callback_query(F.data == "like")
async def kabinet(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Здесь информация о вашей активности", 
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_back_button()]))
    await callback.message.delete()

@dp.callback_query(F.data == "dislike")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Здесь информация о нашем VPN", 
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[get_back_button()]))
    await callback.message.delete()

@dp.callback_query(F.data == "saling")
async def subscription(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Здесь будут условия и цены", 
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                     [InlineKeyboardButton(text="Цена и время", url="https://google.com")],
                                     get_back_button()
                                 ]))
    await callback.message.delete()

async def main():
    init_db() # Создаем таблицу при запуске
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass



   
















