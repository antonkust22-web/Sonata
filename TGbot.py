# -*- coding: utf-8 -*-
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import asyncio

# Текст вынесен отдельно
text1 = "<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI (глубокий анализ трафика)\n✅ Работает в строгих сетях (корпоративных, учебных)\n✅ Простое подключение в один клик\n\nДальше здесь будет информация о подписке"

API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# 1. Главная клавиатура
def get_inline_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подключить устройство", url="https://google.com")], # style удален
        [InlineKeyboardButton(text="🏡 Личный кабинет", callback_data="like")],
        [InlineKeyboardButton(text="👑 Оформление подписки", callback_data="saling")],
        [InlineKeyboardButton(text="📖 Информация", callback_data="dislike")],
    ])
    return keyboard

# Клавиатура для подписки
def get_second_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Цена и время", url="https://google.com")]
    ])

# 2. Обработка /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(text1, parse_mode="HTML", reply_markup=get_inline_keyboard())

# 3. Обработчики кнопок
@dp.callback_query(F.data == "like")
async def kabinet(callback: types.CallbackQuery):
    await callback.answer("Вы зашли в личный кабинет!")
    await callback.message.edit_text("Здесь будет информация о вашей активности")

@dp.callback_query(F.data == "dislike")
async def info(callback: types.CallbackQuery):
    await callback.answer("Вы зашли в раздел информации.")
    await callback.message.edit_text("Здесь будет информация о нашем VPN")

@dp.callback_query(F.data == "saling")
async def subscription(callback: types.CallbackQuery):
    await callback.answer("Вы оформляете подписку!")
    # Добавлены скобки () в вызов функции клавиатуры
    await callback.message.edit_text("Здесь будут условия, цены и так далее", reply_markup=get_second_keyboard())

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")












