import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import asyncio

# Логирование
logging.basicConfig(level=logging.INFO)

# --- НАСТРОЙКИ ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
# ЗАМЕНИТЕ ЭТОТ ID ПОСЛЕ ПОЛУЧЕНИЯ НОВОГО (см. Шаг 1)
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"

WELCOME_TEXT = "<b>Добро пожаловать!</b>\n\nНаш сервис поможет вам оставаться на связи. Нажмите кнопку ниже."
MAIN_TEXT = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает везде\n\nВыберите нужный пункт:"

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
        [InlineKeyboardButton(text="👑 Подписка", callback_data="sub")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="info")],
    ])

def back_btn():
    return [InlineKeyboardButton(text="⬅️ Назад", callback_data="go_to_main")]

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=get_welcome_keyboard())

@dp.callback_query(F.data == "go_to_main")
async def show_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    try:
        # Пытаемся отправить видео
        await callback.message.answer_video(
            video=VIDEO_ID,
            caption=MAIN_TEXT,
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    except Exception as e:
        logging.error(f"Ошибка видео: {e}")
        # Если ID неверный — отправляем просто текст, чтобы бот не "умирал"
        await callback.message.answer(
            "⚠️ Видео загружается или ID устарел.\n\n" + MAIN_TEXT,
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    
    await callback.message.delete()

# Простые разделы
@dp.callback_query(F.data.in_(["kabinet", "sub", "info"]))
async def sections(callback: types.CallbackQuery):
    await callback.answer()
    texts = {
        "kabinet": "Данные вашего аккаунта...",
        "sub": "Цены: 1 месяц - 200р...",
        "info": "Наш VPN работает на протоколах VLESS/Reality"
    }
    await callback.message.answer(texts[callback.data], 
                                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[back_btn()]))
    await callback.message.delete()

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())




















