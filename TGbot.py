import asyncio
import logging
import json
import uuid
import time
import os
import sqlite3 # Используем для жесткого контроля путей при старте
import aiohttp
import aiosqlite  # Используем асинхронный SQLite для работы хендлеров

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

# --- НАСТРОЙКА УНИВЕРСАЛЬНОГО ПУТИ К БД (ВСТАВИТЬ В НАЧАЛО) ---
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "users.db") # База будет создаваться в папке бота на хостинге


# --- Настройки (ОБЯЗАТЕЛЬНО ОБНОВИТЕ ТОКЕН И ПАРОЛЬ) ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
PANEL_URL = "https://78.17.1.43:10096"
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
INBOUND_ID = 1
BASE_PATH = "/XWYB6HCgL7NBchJqxo"

# ТОКЕН ПЛАТЕЖКИ ЮKASSA
PROVIDER_TOKEN = "390540012:LIVE:96775"

# File ID вашего видео
VIDEO_MAIN = "BAACAgIAAxkBAAMLagtRYohK4W-WOfghGVIlBtWuyIoAAjWeAAL-Q1lIcZMozT4F8hw7BA"

text1 = (
    "👋<b>Обходите блокировки легко!</b>\n"
    "✅ Невидим для DPI\n"
    "✅ Работает в строгих сетях\n"
    "✅ Подключение в один клик\n\n"
    "Дальше здесь будет информация о подписке"
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()


# --- База данных (Асинхронная версия с путем на Рабочий стол) ---
async def init_db():
    logging.info(f"Диспетчер: Проверка и создание базы данных по пути: {DB_PATH}")
    async with aiosqlite.connect(DB_PATH, timeout=30.0) as conn:
        await conn.execute('PRAGMA journal_mode=WAL;')
        await conn.execute('PRAGMA synchronous=NORMAL;')
        await conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
        await conn.commit()

async def add_user(user_id):
    async with aiosqlite.connect(DB_PATH, timeout=30.0) as conn:
        await conn.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        await conn.commit()


# --- Асинхронные Функции VPN (X-UI API через aiohttp) ---
async def get_vpn_config_manual(user_id):
    email = f"user_{user_id}"
    connector = aiohttp.TCPConnector(ssl=False)
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            # 1. Логин
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            async with session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10) as resp:
                await resp.text()

            # 2. Получение данных инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            async with session.get(get_url, timeout=10) as resp:
                res_json = await resp.json()
                
            if not res_json.get("success"):
                return None, None

            settings = json.loads(res_json["obj"]["settings"])
            clients = settings.get("clients", [])
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)

            # 3. Создание клиента, если его нет
            if not client_uuid:
                client_uuid = str(uuid.uuid4())
                add_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient"
                client_data = {
                    "id": str(INBOUND_ID),
                    "settings": json.dumps({
                        "clients": [{
                            "id": client_uuid,
                            "email": email,
                            "limitIp": 2,
                            "totalGB": 0,
                            "expiryTime": 0,
                            "enable": True,
                            "tgId": user_id,
                            "subId": ""
                        }]
                    })
                }
                async with session.post(add_url, data=client_data, timeout=10) as resp:
                    await resp.text()

            # 4. Формирование рабочей ссылки
            my_ip = "78.17.1.43"
            my_port = res_json["obj"]["port"]
            pbk = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38"
            sid = "32b6a4ff54ef1812"
            sni = "sony.com"
            country_flag = "🇫🇮"
            country_name = "Финляндия"
            server_type = "Premium"
            remark = f"{country_flag} {country_name}?{server_type}"

            config_link = (
                f"vless://{client_uuid}@{my_ip}:{my_port}"
                f"?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F"
                f"#{remark}"
            )
            return config_link, f"happ://import/{config_link}"
            
    except Exception as e:
        logging.error(f"Ошибка VPN при получении конфига: {e}")
        return None, None

async def renew_vpn_subscription(user_id):
    email = f"user_{user_id}"
    connector = aiohttp.TCPConnector(ssl=False)
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            # 1. Логин
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            async with session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10) as resp:
                await resp.text()
            
            # 2. Получаем текущие данные инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            async with session.get(get_url, timeout=10) as resp:
                res_json = await resp.json()
                
            if not res_json.get("success"):
                logging.error(f"Ошибка панели: не удалось получить инбаунд {INBOUND_ID}")
                return False
                
            settings = json.loads(res_json["obj"]["settings"])
            clients = settings.get("clients", [])
            
            client = next((c for c in clients if c.get("email") == email), None)
            if not client:
                logging.error(f"Пользователь user_{user_id} не найден в панели для продления подписки")
                return False

            # 3. Расчет нового времени (в миллисекундах)
            current_time_ms = int(time.time() * 1000)
            thirty_days_ms = 30 * 24 * 60 * 60 * 1000
            
            if client.get("expiryTime", 0) > current_time_ms:
                new_expiry = client["expiryTime"] + thirty_days_ms
                logging.info(f"Подписка пользователя {user_id} еще активна. Продлеваем от даты окончания.")
            else:
                new_expiry = current_time_ms + thirty_days_ms
                logging.info(f"Подписка пользователя {user_id} истекла или новая. Продлеваем от текущего времени.")

            # 4. Отправляем запрос на обновление клиента (updateClient по UUID)
            client_uuid = client['id']
            update_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/updateClient/{client_uuid}"
            
            client_data = {
                "id": str(INBOUND_ID),
                "settings": json.dumps({
                    "clients": [{
                        "id": client_uuid,
                        "email": email,
                        "limitIp": client.get("limitIp", 2),
                        "totalGB": client.get("totalGB", 0),
                        "expiryTime": new_expiry,
                        "enable": True,
                        "tgId": user_id,
                        "subId": client.get("subId", "")
                    }]
                })
            }
            
            async with session.post(update_url, data=client_data, timeout=10) as resp:
                update_resp = await resp.json()
                
            return update_resp.get("success", False)
            
    except Exception as e:
        logging.error(f"Ошибка при продлении подписки: {e}")
        return False


# --- Клавиатуры ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ) РАЗРАБОТКА", callback_data="connect")],
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="📖 Информация и поддержка", callback_data="info")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])


# --- Хендлеры ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await add_user(message.from_user.id) # Асинхронная запись на Рабочий стол
    await message.answer_video(
        video=VIDEO_MAIN,
        caption=text1,
        reply_markup=main_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer()
    config, _ = await get_vpn_config_manual(callback.from_user.id)
    if config:
        text = f"<b>👤 Личный кабинет</b>\n\n<b>Ваш ID:</b> <code>{callback.from_user.id}</code>\n\n<b>Ваш ключ:</b>\n<code>{config}</code>"
    else:
        text = "❌ Не удалось получить ключ. Проверьте настройки панели."
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=back_kb(), parse_mode="HTML")
    except TelegramBadRequest:
        pass

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer()
    _, happ_url = await get_vpn_config_manual(callback.from_user.id)
    if happ_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
        try:
            await callback.message.edit_caption(
                caption="Нажмите кнопку ниже для импорта в Happ:", 
                reply_markup=kb
            )
        except TelegramBadRequest:
            pass
    else:
        # Этот блок теперь правильно относится к условию "if happ_url:"
        await callback.answer(
            "❌ Ошибка сервера: не удалось сгенерировать ссылку подключения.", 
            show_alert=True
        )

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_caption(
            caption=text1, 
            reply_markup=main_kb(), 
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass

@dp.callback_query(F.data == "info")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        "Новый VPN будет обеспечивать высокую скорость соединения и улучшенную конфиденциальность пользователей. "
        "Планируется внедрение современных протоколов безопасности и удобный интерфейс.\n\n"
        "Тех.поддержка @Sonata_VPN_Admin"
    )
    try:
        await callback.message.edit_caption(
            caption=text, 
            reply_markup=back_kb(), 
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass

@dp.callback_query(F.data == "buy")
async def subscription(callback: types.CallbackQuery):
    await callback.answer()
    buy_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить 150 руб. / месяц", callback_data="pay_30_days")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])
    try:
        await callback.message.edit_caption(
            caption="Выбор тарифа:\n\nПодписка на 30 дней снимет ограничения по времени работы ключа.",
            reply_markup=buy_kb,
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass

@dp.callback_query(F.data == "pay_30_days")
async def send_invoice(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    await get_vpn_config_manual(callback.from_user.id)
    logging.info(f"Диспетчер: Отправка инвойса пользователю {callback.from_user.id}")
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Подписка на VPN (30 дней)",
        description="Продление доступа к высокоскоростному VPN Sonata на 1 месяц.",
        payload="vpn_30_days_subscription",
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="16 месяц подписки", amount=15000)],
        start_parameter="vpn-sub-30-days"
    )

# --- Валидация платежа перед списанием средств ---
@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: types.PreCheckoutQuery, bot: Bot):
    logging.info(f"Диспетчер: Получен запрос PreCheckoutQuery от пользователя {pre_checkout_query.from_user.id}.")
    try:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
        logging.info(f"Диспетчер: Запрос PreCheckoutQuery для {pre_checkout_query.from_user.id} успешно подтвержден.")
    except Exception as e:
        logging.error(f"Ошибка в обработке pre_checkout_query: {e}")

# --- Обработка успешного платежа ---
@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    total_amount = message.successful_payment.total_amount / 100
    logging.info(f"Диспетчер: ПОЛУЧЕН УСПЕШНЫЙ ПЛАТЕЖ! Пользователь: {user_id}, Сумма: {total_amount} RUB")
    
    if payload == "vpn_30_days_subscription":
        logging.info(f"Диспетчер: Запуск функции продления подписки в X-UI для {user_id}...")
        success = await renew_vpn_subscription(user_id)
        config, happ_url = await get_vpn_config_manual(user_id)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        if happ_url:
            kb.inline_keyboard.append([InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)])
            
        if success:
            logging.info(f"Диспетчер: Подписка в панели X-UI для {user_id} успешно продлена.")
            await message.answer(
                f"✅ <b>Оплата прошла успешно!</b>\n"
                f"Ваша подписка успешно продлена на 30 дней.\n\n"
                f"<b>Ваш ключ подключения VLESS:</b>\n"
                f"<code>{config if config else 'Ошибка генерации текста ключа'}</code>\n\n"
                f"Вы можете скопировать этот ключ или нажать кнопку ниже для импорта.",
                reply_markup=kb if happ_url else None,
                parse_mode="HTML"
            )
        else:
            logging.error(f"Диспетчер КРИТИЧЕСКАЯ ОШИБКА: Деньги от {user_id} получены, но функция renew_vpn_subscription вернула False!")
            await message.answer(
                f"⚠️ <b>Оплата прошла успешно, но возник сбой синхронизации с сервером!</b>\n"
                f"Не переживайте, ваш доступ активирован. Администратор уже уведомлен и исправит отображение дней.\n\n"
                f"<b>Ваш рабочий ключ для подключения:</b>\n"
                f"<code>{config if config else 'Пожалуйста, обратитесь в поддержку для получения ключа'}</code>\n\n"
                f"Если ключ не работает, свяжитесь с поддержкой: @Sonata_VPN_Admin\n"
                f"Ваш ID: <code>{user_id}</code>",
                reply_markup=kb if happ_url else None,
                parse_mode="HTML"
            )

# --- Запуск ---
async def main():
    # Жесткое синхронное создание пустого файла на Рабочем столе перед стартом бота
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, 'w') as f:
            pass
        logging.info(f"Диспетчер: Файл базы данных физически создан на Рабочем столе: {DB_PATH}")
        
    # Асинхронная инициализация таблиц SQLite
    await init_db()
    logging.info("Диспетчер: База данных успешно инициализирована таблицами.")
    logging.info("Диспетчер: Бот успешно запущен и начинает опрос серверов Telegram (Polling)...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())



