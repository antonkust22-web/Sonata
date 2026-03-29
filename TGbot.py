from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import asyncio

API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# 1. Создаем клавиатуру с кнопками
def get_inline_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 Лайк", callback_data="like"),
            InlineKeyboardButton(text="👎 Дизлайк", callback_data="dislike")
        ],
        [InlineKeyboardButton(text="Открыть сайт", url="https://google.com")]
    ])
    return keyboard

# 2. Отправляем сообщение с кнопками
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Оцените сообщение:", reply_markup=get_inline_keyboard())

# 3. Обрабатываем нажатия
@dp.callback_query(F.data == "like")
async def send_random_value(callback: types.CallbackQuery):
    await callback.answer("Вам понравилось!") # Убирает "часики" на кнопке
    await callback.message.edit_text("Спасибо за лайк! 👍")

@dp.callback_query(F.data == "dislike")
async def send_random_value(callback: types.CallbackQuery):
    await callback.answer("Вам не понравилось!")
    await callback.message.edit_text("Нам жаль... 👎")

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

