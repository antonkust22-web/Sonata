from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
VIDEO_ID = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"
text1 = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает везде\n✅ Один клик\n\nДальше здесь будет информация о подписке"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Клавиатуры ---

def get_welcome_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать использование", callback_data="go_to_menu")]
    ])

def get_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подключить устройство", url="https://google.com")],
        [InlineKeyboardButton(text="🏡 Личный кабинет", callback_data="like")],
        [InlineKeyboardButton(text="👑 Оформление подписки", callback_data="saling")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="dislike")],
    ])

def get_back_button():
    return [InlineKeyboardButton(text="⬅️ На главную", callback_data="go_to_menu")]

def get_second_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цена и время", url="https://google.com")],
        get_back_button()
    ])

def only_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[get_back_button()])

# --- Хендлеры ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Первое приветственное сообщение
    await message.answer(
        "👋 <b>Добро пожаловать в наш VPN сервис!</b>\n\nМы поможем вам получить свободный доступ в интернет без ограничений.",
        parse_mode="HTML",
        reply_markup=get_welcome_kb()
    )

@dp.callback_query(F.data == "go_to_menu")
async def show_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    try:
        # Удаляем предыдущее сообщение (приветствие или инфо-раздел)
        await callback.message.delete()
        
        # Отправляем видео и главное меню
        await callback.message.answer_video(
            video=VIDEO_ID,
            caption=text1,
            parse_mode="HTML",
            reply_markup=get_inline_keyboard()
        )
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await callback.message.answer(text1, parse_mode="HTML", reply_markup=get_inline_keyboard())

@dp.callback_query(F.data == "like")
async def kabinet(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_caption(caption="👤 <b>Личный кабинет</b>\n\nЗдесь информация о вашей активности", 
                                        parse_mode="HTML", reply_markup=only_back_keyboard())

@dp.callback_query(F.data == "dislike")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_caption(caption="📖 <b>Информация</b>\n\nЗдесь информация о нашем VPN", 
                                        parse_mode="HTML", reply_markup=only_back_keyboard())

@dp.callback_query(F.data == "saling")
async def subscription(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_caption(caption="💳 <b>Подписка</b>\n\nЗдесь будут условия и цены", 
                                        parse_mode="HTML", reply_markup=get_second_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
