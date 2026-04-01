# -*- coding: utf-8 -*-
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
from aiogram.filters import Command
import asyncio
import logging

# Включаем логирование, чтобы видеть ошибки в консоли
logging.basicConfig(level=logging.INFO)

text1 = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI (глубокий анализ трафика)\n✅ Работает в строгих сетях (корпоративных, учебных)\n✅ Простое подключение в один клик\n\nДальше здесь будет информация о подписке"
VIDEO_URL = "BAACAgIAAxkBAAMFac1lT_rLVMdl6y5cW3ZZdTtSjDAAAnafAAIMoHFKjUalcja6GxU6BA"

API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

def get_inline_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подключить устройство", url="https://google.com")],
        [InlineKeyboardButton(text="🏡 Личный кабинет", callback_data="like")],
        [InlineKeyboardButton(text="👑 Оформление подписки", callback_data="saling")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="dislike")],
    ])

def get_back_button():
    return [InlineKeyboardButton(text="⬅️ На главную", callback_data="back_to_main")]

def get_second_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цена и время", url="https://google.com")],
        get_back_button()
    ])

def only_back_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[get_back_button()])

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    try:
        # Используем URLInputFile для надежности
        video = URLInputFile(VIDEO_URL)
        await message.answer_video(
            video=video,
            caption=text1,
            parse_mode="HTML",
            reply_markup=get_inline_keyboard()
        )
    except Exception as e:
        logging.error(f"Ошибка отправки видео: {e}")
        # Если видео не грузится, отправляем просто текст, чтобы бот работал
        await message.answer(text1 + "\n\n(Видео временно недоступно)", parse_mode="HTML", reply_markup=get_inline_keyboard())

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.delete()
    # Вызываем функцию старта, чтобы снова прислать видео
    await cmd_start(callback.message)

@dp.callback_query(F.data == "like")
async def kabinet(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Здесь информация о вашей активности", reply_markup=only_back_keyboard())
    await callback.message.delete()

@dp.callback_query(F.data == "dislike")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Здесь информация о нашем VPN", reply_markup=only_back_keyboard())
    await callback.message.delete()

@dp.callback_query(F.data == "saling")
async def subscription(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Здесь будут условия и цены", reply_markup=get_second_keyboard())
    await callback.message.delete()

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass















