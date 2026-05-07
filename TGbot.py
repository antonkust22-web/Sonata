import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command

# --- Настройки (ВСТАВЬТЕ СВОЙ НОВЫЙ ТОКЕН) ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI' 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Убираем видео, убираем базу данных, только текст
    await message.answer(
        f"✅ СВЯЗЬ УСТАНОВЛЕНА!\n\n"
        f"Привет, {message.from_user.first_name}.\n"
        f"Если ты видишь это сообщение, значит хостинг и токен работают.\n"
        f"Теперь мы можем по очереди добавлять VPN и базу данных."
    )

async def main():
    print("!!! БОТ ЗАПУСКАЕТСЯ В ТЕСТОВОМ РЕЖИМЕ !!!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Критическая ошибка: {e}")


