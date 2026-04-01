from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import asyncio

text1 = "<b>Обходите белый список легко!< /b>\n✅Невидим для DPI (глубокий анализ трафик\n✅Работает в строгих сетях (корпоративных, учебных)\n✅Простое подключение в один клик\nдальше здесь будет информция о подписке"
#✅Невидим для DPI (глубокий анализ трафик)
#✅Работает в строгих сетях (корпоративных, учебных)
#✅Простое подключение в один клик
#дальше здесь будет информция о подписке

#Привет!\nЯ твой бот.\nВыберите команду:



API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# 1. Создаем клавиатуру с кнопками
def get_inline_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подключить устройство", url="https://google.com", style = 'success')],
            
            [InlineKeyboardButton(text="🏡Личный кабинет", callback_data="like")],
            [InlineKeyboardButton(text="👑Оформление подписки", callback_data="saling")],
            [InlineKeyboardButton(text="📖Информация", callback_data="dislike")],
            
    ])
    return keyboard



# 2. Отправляем сообщение с кнопками
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(text1, parse_mode="HTML", reply_markup=get_inline_keyboard())

# 3. Обрабатываем нажатия
@dp.callback_query(F.data == "like")
async def send_random_value(callback: types.CallbackQuery):
    await callback.answer("Вы зашли в личный кабинет!") # Убирает "часики" на кнопке
    await callback.message.edit_text("Здесь будет инофрмация о вашей активности")

@dp.callback_query(F.data == "dislike")
async def send_random_value(callback: types.CallbackQuery):
    await callback.answer("Вы зашли в раздел информации.")
    await callback.message.edit_text("Здесь будет информация о нашем VPN")

@dp.callback_query(F.data == "saling")
async def send_random_value(callback: types.CallbackQuery):
    await callback.answer("Вы оформляете подписку!")
    await callback.message.edit_text("Здесь будут условия, цены и так далее", reply_markup=get_second_keyboard)
    
@dp.callback_query(F.text == "saling")
def get_second_keyboard():
    button = InlineKeyboardMarkup(in_keyboard=[[InlineKeyboardButton(text="Цена и время", url="https://google.com" )]])





async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())











