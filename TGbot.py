import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# Настройка логирования
logging.basicConfig(level=logging.INFO)

API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'

WELCOME_TEXT = "<b>Добро пожаловать!</b>\n\nНаш сервис поможет вам оставаться на связи без ограничений."
MAIN_TEXT = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает в строгих сетях\n\nВыберите действие:"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- КЛАВИАТУРЫ ---
def get_welcome_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать работу", callback_data="go_to_main")]
    ])

def get_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подключить устройство", url="https://google.com")],
        [InlineKeyboardButton(text="🏡 Личный кабинет", callback_data="kabinet")],
        [InlineKeyboardButton(text="👑 Оформление подписки", callback_data="sub")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="info")],
    ])

def back_btn():
    return [InlineKeyboardButton(text="⬅️ На главную", callback_data="go_to_main")]

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Отправляем новое чистое сообщение
    await message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=get_welcome_kb())

@dp.callback_query(F.data == "go_to_main")
async def show_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    # Редактируем текст текущего сообщения
    await callback.message.edit_text(
        text=MAIN_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_kb()
    )

@dp.callback_query(F.data.in_(["kabinet", "sub", "info"]))
async def sections(callback: types.CallbackQuery):
    await callback.answer()
    
    texts = {
        "kabinet": "Здесь информация о вашей активности",
        "sub": "Здесь будут условия и цены",
        "info": "Здесь информация о нашем VPN"
    }
    
    kb_list = [[InlineKeyboardButton(text="Цена и время", url="https://google.com")]] if callback.data == "sub" else []
    kb_list.append([back_btn()[0]])
    
    await callback.message.edit_text(
        text=texts[callback.data],
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list)
    )

async def main():
    # skip_updates=True (через drop_pending_updates) очистит очередь старых ошибок
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
