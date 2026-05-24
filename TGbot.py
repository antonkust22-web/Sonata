import asyncio
import logging
import sqlite3
import requests
import json
import uuid
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.filters import Command

# --- Настройки (ОБЯЗАТЕЛЬНО ОБНОВИТЕ ТОКЕН И ПАРОЛЬ) ---
API_TOKEN = '8728088789:AAGfyqAhbg2Ola2BE3n5duGV_LKPgPcT6AI'
PANEL_URL = "https://78.17.1.43:10096"
PANEL_USER = "Asad"
PANEL_PASSWORD = "Lodka120259"
INBOUND_ID = 1
BASE_PATH = "/XWYB6HCgL7NBchJqxo"

# ТОКЕН ПЛАТЕЖКИ ЮKASSA (Получить в @BotFather)
PROVIDER_TOKEN = "390540012:LIVE:96775"

text1 = "👋<b>Обходите блокировки легко!</b>\n✅ Невидим для DPI\n✅ Работает в строгих сетях\n✅ Подключение в один клик\n\nДальше здесь будет информация о подписке"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- База данных ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

def add_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

# --- Функция VPN ---
def get_vpn_config_manual(user_id):
    email = f"user_{user_id}"
    try:
        with requests.Session() as session:
            session.verify = False
            # 1. Логин
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10)
            # 2. Получение данных инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            resp = session.get(get_url, timeout=10).json()
            if not resp.get("success"):
                return None, None
            settings = json.loads(resp["obj"]["settings"])
            clients = settings.get("clients", [])
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)
            # 3. Создание клиента, если его нет
            if not client_uuid:
                client_uuid = str(uuid.uuid4())
                add_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient"
                client_data = {
                    "id": INBOUND_ID,
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
                session.post(add_url, data=client_data, timeout=10)
            # 4. Формирование рабочей ссылки по вашему образцу
            my_ip = "78.17.1.43"
            my_port = resp["obj"]["port"]
            pbk = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38"
            sid = "32b6a4ff54ef1812"
            sni = "://sony.com"
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
        logging.error(f"Ошибка VPN: {e}")
        return None, None

# --- Продление подписки в X-UI на 30 дней ---
def renew_vpn_subscription(user_id):
    email = f"user_{user_id}"
    try:
        with requests.Session() as session:
            session.verify = False
            # 1. Логин
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10)
            
            # 2. Получаем текущие данные инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            resp = session.get(get_url, timeout=10).json()
            if not resp.get("success"):
                logging.error(f"Ошибка панели: не удалось получить инбаунд {INBOUND_ID}")
                return False
                
            settings = json.loads(resp["obj"]["settings"])
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

            # 4. Отправляем запрос на обновление клиента (updateClient)
            update_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/updateClient/{client['id']}"
            
            client_data = {
                "id": INBOUND_ID,
                "settings": json.dumps({
                    "clients": [{
                        "id": client['id'],
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
            
            update_resp = session.post(update_url, data=client_data, timeout=10).json()
            return update_resp.get("success", False)
            
    except Exception as e:
        logging.error(f"Ошибка при продлении подписки: {e}")
        return False

# --- Вставьте сюда ваш проверенный File ID, который заработал! ---
VIDEO_MAIN = "BAACAgIAAxkBAAMLagtRYohK4W-WOfghGVIlBtWuyIoAAjWeAAL-Q1lIcZMozT4F8hw7BA"

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
    add_user(message.from_user.id)
    await message.answer_video(
        video=VIDEO_MAIN,
        caption=text1,
        reply_markup=main_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer()
    config, _ = get_vpn_config_manual(callback.from_user.id)
    if config:
        text = f"<b>👤 Личный кабинет</b>\n\n<b>Ваш ID:</b> <code>{callback.from_user.id}</code>\n\n<b>Ваш ключ:</b>\n<code>{config}</code>"
    else:
        text = "❌ Не удалось получить ключ. Проверьте настройки панели."
    await callback.message.edit_caption(caption=text, reply_markup=back_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer()
    _, happ_url = get_vpn_config_manual(callback.from_user.id)
    if happ_url:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])
        await callback.message.edit_caption(caption="Нажмите кнопку ниже для импорта в Happ:", reply_markup=kb)
    else:
        await callback.answer("❌ Ошибка сервера", show_alert=True)

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.edit_caption(caption=text1, reply_markup=main_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "info")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        "Новый VPN будет обеспечивать высокую скорость соединения и улучшенную конфиденциальность пользователей. "
        "Планируется внедрение современных протоколов безопасности и удобный интерфейс.\n\n"
        "Тех.поддержка @Sonata_VPN_Admin"
    )
    await callback.message.edit_caption(caption=text, reply_markup=back_kb())

@dp.callback_query(F.data == "buy")
async def subscription(callback: types.CallbackQuery):
    await callback.answer()
    buy_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить 150 руб. / месяц", callback_data="pay_30_days")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])
await callback.message.edit_caption(
        caption="<b>Выбор тарифа:</b>\n\nПодписка на 30 дней снимет ограничения по времени работы ключа.", 
        reply_markup=buy_kb, 
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "pay_30_days")
async def send_invoice(callback: types.CallbackQuery):
    await callback.answer()
    # Создаем запись пользователя в панели перед отправкой счета
    get_vpn_config_manual(callback.from_user.id)
    
    logging.info(f"Диспетчер: Отправка инвойса пользователю {callback.from_user.id}")
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Подписка на VPN (30 дней)",
        description="Продление доступа к высокоскоростному VPN Sonata на 1 месяц.",
        payload="vpn_30_days_subscription",
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="1 месяц подписки", amount=15000)],
        start_parameter="vpn-sub-30-days"
    )

# --- ДОБАВЛЕНО ЛОГИРОВАНИЕ: Проверка доступности товара перед списанием средств ---
@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: types.PreCheckoutQuery):
    logging.info(f"Диспетчер: Получен запрос PreCheckoutQuery от пользователя {pre_checkout_query.from_user.id}. Проверяем платеж...")
    # Даем команду Telegram, что товар в наличии и мы готовы принять оплату
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    logging.info(f"Диспетчер: Запрос PreCheckoutQuery для {pre_checkout_query.from_user.id} успешно подтвержден.")

# --- ДОБАВЛЕНО ЛОГИРОВАНИЕ: Перехват успешного платежа и применение изменений ---
@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    total_amount = message.successful_payment.total_amount / 100 # переводим обратно из копеек в рубли
    
    logging.info(f"Диспетчер: ПОЛУЧЕН УСПЕШНЫЙ ПЛАТЕЖ! Пользователь: {user_id}, Сумма: {total_amount} RUB, Payload: {payload}")
    
    if payload == "vpn_30_days_subscription":
        logging.info(f"Диспетчер: Запуск функции продления подписки в X-UI для {user_id}...")
        success = renew_vpn_subscription(user_id)
        
        if success:
            logging.info(f"Диспетчер: Подписка в панели X-UI для {user_id} успешно продлена.")
            await message.answer(
                "✅ <b>Оплата прошла успешно!</b>\n"
                "Ваша подписка успешно продлена на 30 дней.\n"
                "Проверить статус можно в личном кабинете под главным видео.",
                parse_mode="HTML"
            )
        else:
            logging.error(f"Диспетчер КРИТИЧЕСКАЯ ОШИБКА: Деньги от {user_id} получены, но X-UI панель вернула ошибку при продлении подписки!")
            await message.answer(
                "⚠️ <b>Деньги получены, но возникла ошибка панели!</b>\n"
                "Пожалуйста, свяжитесь с администратором @Sonata_VPN_Admin для ручного продления. "
                f"Укажите ваш ID: <code>{user_id}</code>",
                parse_mode="HTML"
            )

# --- Запуск ---
async def main():
    init_db()
    requests.packages.urllib3.disable_warnings()
    logging.info("Диспетчер: Бот успешно запущен и начинает опрос серверов Telegram (Polling)...")
    await dp.start_polling(bot)

if name == '__main__':
    asyncio.run(main())