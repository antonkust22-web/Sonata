import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import asyncio

# Логирование
logging.basicConfig(level=logging.INFO)

# --- НАСТРОЙКИ ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
# Если видео не грузится, пришлите видео боту, получите новый ID и замените его здесь
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"

WELCOME_TEXT = "<b>Добро пожаловать!</b>\n\nНаш сервис поможет вам оставаться на связи без ограничений. Нажмите кнопку ниже, чтобы перейти к настройкам."
MAIN_TEXT = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает в строгих сетях\n✅ Простое подключение в один клик\n\nДальше здесь будет информация о подписке"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- КЛАВИАТУРЫ ---
def get_welcome_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать работу", callback_data="go_to_main")]
    ])

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подключить устройство", url="https://google.com")],
        [InlineKeyboardButton(text="🏡 Личный кабинет", callback_data="kabinet")],
        [InlineKeyboardButton(text="👑 Оформление подписки", callback_data="sub")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="info")],
    ])

def back_btn():
    return [InlineKeyboardButton(text="⬅️ На главную", callback_data="go_to_main")]

# --- ОБРАБОТЧИКИ ---

# 1. Команда старт (Приветствие)
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=get_welcome_keyboard())

# 2. Главное меню (с видео)
@dp.callback_query(F.data == "go_to_main")
async def show_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.answer_video(
            video=VIDEO_ID,
            caption=MAIN_TEXT,
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logging.error(f"Ошибка видео: {e}")
        # Запасной вариант, если VIDEO_ID неверный
        await callback.message.answer(
            "⚠️ Видео временно недоступно.\n\n" + MAIN_TEXT,
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    try:
        await callback.message.delete()
    except:
        pass

# 3. Подразделы (Кабинет, Подписка, Инфо)
@dp.callback_query(F.data.in_(["kabinet", "sub", "info"]))
async def sections(callback: types.CallbackQuery):
    await callback.answer()
    
    texts = {
        "kabinet": "Здесь информация о вашей активности",
        "sub": "Здесь будут условия и цены",
        "info": "Здесь информация о нашем VPN"
    }
    
    # Для подписки используем вашу структуру кнопок (Цена + Назад)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цена и время", url="https://google.com")],
        back_btn()
    ]) if callback.data == "sub" else InlineKeyboardMarkup(inline_keyboard=[back_btn()])

    await callback.message.answer(texts[callback.data], reply_markup=kb)
    await callback.message.delete()

# 4. СЛУЖЕБНЫЙ ХЕНДЛЕР: Пришлите видео боту, чтобы узнать новый VIDEO_ID
@dp.message(F.video)
async def get_video_id(message: types.Message):
    await message.answer(f"Ваш новый VIDEO_ID:\n<code>{message.video.file_id}</code>", parse_mode="HTML")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass





















