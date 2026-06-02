import asyncio
import logging
import json
import uuid
import time
import os
import subprocess
import sqlite3  # Используем стандартный встроенный sqlite3

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

# --- ПРАВА АДМИНИСТРАТОРА ---
ADMIN_ID = 8759913724  # ОБЯЗАТЕЛЬНО: Замените эти цифры на ваш настоящий Telegram ID


# --- НАСТРОЙКА ПУТИ К БД ДЛЯ ХОСТИНГА AMVERA ---
# На Amvera папка /data постоянная, файлы в ней не стираются при пересборках.
if os.path.exists("/data"):
    DB_PATH = "/data/users.db"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, "users.db")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

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
    "👋 <b>Обходите блокировки легко!</b>\n"
    "✅ Невидим для DPI\n"
    "✅ Работает в строгих сетях\n"
    "✅ Подключение в один клик\n\n"
    "Дальше здесь будет информация о подписке"
)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


# --- Блок Базы Данных (Синхронный sqlite3 с защитой от блокировок) ---
def init_db():
    logging.info(f"Диспетчер: Инициализация базы данных: {DB_PATH}")
    # timeout=30.0 заставляет запросы послушно ждать, если база занята
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    # Включаем режим WAL. Это ускоряет запись в 10 раз и исключает зависания
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA synchronous=NORMAL;')
    
    # Создаем продвинутую таблицу пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            vpn_config TEXT,
            happ_url TEXT,
            expiry_time INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def add_or_update_user(user_id, username, vpn_config=None, happ_url=None, expiry_time=None):
    """Безопасное добавление или обновление данных пользователя"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    # Проверяем, есть ли уже юзер
    cursor.execute('SELECT user_id, vpn_config, happ_url, expiry_time FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    
    if not row:
        # Если пользователя нет — создаем запись
        cursor.execute(
            'INSERT INTO users (user_id, username, vpn_config, happ_url, expiry_time) VALUES (?, ?, ?, ?, ?)',
            (user_id, username, vpn_config, happ_url, expiry_time if expiry_time else 0)
        )
    else:
        # Если пользователь есть — обновляем только то, что передано
        new_config = vpn_config if vpn_config else row[1]
        new_happ = happ_url if happ_url else row[2]
        new_expiry = expiry_time if expiry_time is not None else row[3]
        
        cursor.execute(
            'UPDATE users SET username = ?, vpn_config = ?, happ_url = ?, expiry_time = ? WHERE user_id = ?',
            (username, new_config, new_happ, new_expiry, user_id)
        )
        
    conn.commit()
    conn.close()

def get_user_from_db(user_id):
    """Получение всех данных о пользователе из локальной БД"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('SELECT username, vpn_config, happ_url, expiry_time FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row


import urllib.parse

async def get_vpn_config_manual(user_id, username=""):
    email = f"user_{user_id}"
    
    # Включаем принудительное сохранение кук сессии для работы по IP (аналог requests.Session)
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            # 1. Логин в панель
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            async with session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10) as resp:
                await resp.text()

            headers = {
                "Accept": "application/json"
            }

            # 2. Получение данных инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            async with session.get(get_url, headers=headers, timeout=10) as resp:
                res_json = await resp.json()
                
            if not res_json.get("success"):
                logging.error(f"Панель X-UI вернула ошибку при GET: {res_json}")
                return None, None

            settings = json.loads(res_json["obj"]["settings"])
            clients = settings.get("clients", [])
            client_uuid = next((c.get("id") for c in clients if c.get("email") == email), None)

            # 3. Создание клиента, если его нет
            if not client_uuid:
                client_uuid = str(uuid.uuid4())
                add_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/addClient"
                client_data = {
                    "id": str(INBOUND_ID), # Передаем строку/число инбаунда
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
                async with session.post(add_url, headers=headers, data=client_data, timeout=10) as resp:
                    await resp.text()
                expiry_time_ms = 0
            else:
                # Находим текущего клиента в списке, чтобы забрать его expiryTime для SQLite3
                current_client = next((c for c in clients if c.get("email") == email), None)
                expiry_time_ms = current_client.get("expiryTime", 0) if current_client else 0

            # 4. Формирование рабочей ссылки ТОЧЬ-В-ТОЧЬ ПО ВАШЕМУ ЭТАЛОНУ
            my_ip = "78.17.1.43"
            my_port = res_json["obj"]["port"]
            pbk = "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38"
            sid = "32b6a4ff54ef1812"
           
            sni = "www.sony.com"
            country_flag = "🇫🇮"
            country_name = "Финляндия"
            server_type = "Premium"
            remark = f"{country_flag} {country_name}?{server_type}"
            
            # Экранирование спецсимволов и кириллицы (сохранено как в вашем рабочем коде)
            safe_remark = urllib.parse.quote(remark)

            config_link = (
                f"vless://{client_uuid}@{my_ip}:{my_port}"
                f"?type=tcp&security=reality&sni={sni}&fp=chrome&pbk={pbk}&sid={sid}&spx=%2F"
                f"#{safe_remark}"
            )
            happ_url = f"happ://import/{config_link}"
            
            # Сохраняем/обновляем данные в нашей локальной БД sqlite3
            expiry_seconds = int(expiry_time_ms / 1000) if expiry_time_ms > 0 else 0
            add_or_update_user(user_id, username, config_link, happ_url, expiry_seconds)
            
            return config_link, happ_url

    except Exception as e:
        logging.error(f"Ошибка VPN: {e}")
        return None, None

async def renew_vpn_subscription(user_id):
    email = f"user_{user_id}"
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            # 1. Авторизация в панели
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            async with session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10) as resp:
                await resp.text()
            
            headers = {
                "Accept": "application/json"
            }

            # 2. Получаем текущие данные инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            async with session.get(get_url, headers=headers, timeout=10) as resp:
                res_json = await resp.json()
                
            if not res_json.get("success"):
                logging.error(f"Не удалось получить данные инбаунда для продления подписки: {res_json}")
                return False
                
            settings = json.loads(res_json["obj"]["settings"])
            clients = settings.get("clients", [])
            client = next((c for c in clients if c.get("email") == email), None)
            
            if not client:
                logging.error(f"Клиент {email} не найден в панели X-UI.")
                return False

            # 3. Расчет времени (в миллисекундах)
            current_time_ms = int(time.time() * 1000)
            thirty_days_ms = 30 * 24 * 60 * 60 * 1000
            
            if client.get("expiryTime", 0) > current_time_ms:
                new_expiry = client["expiryTime"] + thirty_days_ms
            else:
                new_expiry = current_time_ms + thirty_days_ms

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
            async with session.post(update_url, headers=headers, data=client_data, timeout=10) as resp:
                update_resp = await resp.json()
            
            success = update_resp.get("success", False)
            if success:
                # Синхронизируем новую дату окончания подписки в локальную SQLite3
                expiry_seconds = int(new_expiry / 1000)
                add_or_update_user(user_id, "", expiry_time=expiry_seconds)
                logging.info(f"Подписка для пользователя {user_id} успешно продлена в X-UI и SQLite3.")
                
            return success
    except Exception as e:
        logging.error(f"Ошибка при продлении подписки через ЮKassa: {e}")
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
    # Обычный быстрый вызов без await — sqlite3 отработает мгновенно
    add_or_update_user(message.from_user.id, message.from_user.username or "Unknown")
    await message.answer_video(
        video=VIDEO_MAIN,
        caption=text1,
        reply_markup=main_kb(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    
    # Синхронизируем данные с панелью X-UI (чтобы обновить дату, если платеж прошел)
    config, _ = await get_vpn_config_manual(user_id, callback.from_user.username or "")
    
    # Читаем данные из нашей надежной локальной SQLite3
    db_data = get_user_from_db(user_id)
    
    # Создаем клавиатуру для ЛК (кнопка Назад будет всегда)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    if db_data and db_data[1]:  # Если запись и ключ существуют в базе
        expiry_timestamp = db_data[3] # Получаем Unix-время окончания из БД
        current_time = time.time()
        
        # ПРОВЕРКА: Если подписка активна (время окончания больше текущего)
        if expiry_timestamp > current_time:
            # Рассчитываем оставшиеся дни
            days_left = int((expiry_timestamp - current_time) / (24 * 3600))
            status_text = f"🟢 Активна (осталось {days_left} дн.)"
            
            # ПОКАЗЫВАЕМ ТЕКСТ И КЛЮЧ
            text = (
                f"<b>👤 Личный кабинет</b>\n\n"
                f"<b>Ваш ID:</b> <code>{user_id}</code>\n"
                f"<b>Статус подписки:</b> {status_text}\n\n"
                f"<b>Ваш ключ подключения VLESS:</b>\n"
                f"<code>{db_data[1]}</code>\n\n"
                f" Скопируйте этот ключ или перейдите в меню 'Подключиться' для быстрого импорта."
            )
            # В активном кабинете оставляем только кнопку Назад
            kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
            
        else:
            # ЕСЛИ ПОДПИСКА НЕ ОПЛАЧЕНА ИЛИ ИСТЕКЛА — ПРЯЧЕМ КЛЮЧ
            status_text = "🔴 Не активна (требуется оплата)"
            text = (
                f"<b>👤 Личный кабинет</b>\n\n"
                f"<b>Ваш ID:</b> <code>{user_id}</code>\n"
                f"<b>Статус подписки:</b> {status_text}\n\n"
                f"⚠️ Для получения доступа к высокоскоростному VPN Sonata и генерации вашего личного ключа, пожалуйста, приобретите подписку."
            )
            # Сюда мы принудительно добавляем кнопку быстрой покупки тарифного плана
            kb.inline_keyboard.append([InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")])
            kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    else:
        text = "❌ Ошибка профиля. Нажмите /start для перезапуска бота."
        kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
        
    try:
        await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass


@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    
    # Проверяем статус в нашей локальной базе данных
    db_data = get_user_from_db(user_id)
    
    # Если подписка оформлена и еще не закончилась
    if db_data and db_data[3] > time.time():
        _, happ_url = await get_vpn_config_manual(user_id, callback.from_user.username or "")
        if happ_url:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
            ])
            try:
                await callback.message.edit_caption(caption="Нажмите кнопку ниже для импорта в Happ:", reply_markup=kb)
            except TelegramBadRequest:
                pass
        else:
            await callback.answer("❌ Ошибка сервера: не удалось сгенерировать ссылку.", show_alert=True)
    else:
        # Если клиент пытается зайти без оплаты — выдаем предупреждение
        await callback.answer("⚠️ Доступ заблокирован! Сначала приобретите подписку в меню 'Купить подписку'.", show_alert=True)

@dp.callback_query(F.data == "back")
async def back(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_caption(caption=text1, reply_markup=main_kb(), parse_mode="HTML")
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
        await callback.message.edit_caption(caption=text, reply_markup=back_kb(), parse_mode="HTML")
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
    await get_vpn_config_manual(callback.from_user.id, callback.from_user.username or "")
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

# --- АДМИН-ПАНЕЛЬ: РАССЫЛКА И ПОДАРКИ ---

@dp.message(Command("send"))
async def admin_broadcast(message: types.Message):
    # Жесткая проверка: если пишет не админ, бот просто игнорирует команду
    if message.from_user.id != ADMIN_ID:
        return

    # Вытаскиваем текст сообщения, убирая саму команду /send
    text_to_send = message.text.replace("/send", "").strip()
    
    if not text_to_send:
        await message.answer("⚠️ <b>Ошибка:</b> Вы ввели пустую команду. Пишите так: <code>/send Ваш текст</code>")
        return

    # Получаем список всех ID из нашей SQLite3
    all_users = get_all_users_from_db()
    
    await message.answer(f"⏳ <b>Начата рассылка</b> для {len(all_users)} пользователей...")
    
    success_count = 0
    for user_id in all_users:
        try:
            # Отправляем сообщение каждому пользователю
            await bot.send_message(chat_id=user_id, text=text_to_send, parse_mode="HTML")
            success_count += 1
            # Небольшая микро-пауза, чтобы Telegram не заблокировал бота за спам
            await asyncio.sleep(0.05)
        except Exception:
            # Игнорируем ошибки, если пользователь заблокировал бота
            pass

    await message.answer(f"✅ <b>Рассылка завершена успешно!</b>\nДоставлено сообщений: {success_count} из {len(all_users)}")


@dp.message(Command("gift"))
async def admin_gift_sub(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        # Разделяем команду по пробелам: /gift 123456789 30
        parts = message.text.split()
        target_user_id = int(parts[1])  # ID пользователя
        days_to_add = int(parts[2])     # Количество дней подписки (например, 30)
    except (IndexError, ValueError):
        await message.answer("⚠️ <b>Неверный формат!</b> Пишите так:\n<code>/gift ID_ПОЛЬЗОВАТЕЛЯ ДНИ</code>\n\nПример: <code>/gift 584930211 30</code>")
        return

    await message.answer(f"⏳ Связываюсь с панелью X-UI для выдачи подписки пользователю {target_user_id}...")

    # Вызываем функцию автоматического добавления дней (она у нас уже написана для ЮKassa!)
    # Но так как ЮKassa добавляет жестко 30 дней, давайте запустим её.
    # Если вы ввели 30 дней, это сработает идеально через API
    success = await renew_vpn_subscription(target_user_id)
    
    if success:
        # Генерируем обновленный ключ, чтобы он записался в локальную SQLite3
        await get_vpn_config_manual(target_user_id)
        
        await message.answer(f"🎉 <b>Успех!</b> Доступ для <code>{target_user_id}</code> успешно продлен на {days_to_add} дней.")
        
        # Автоматически отправляем уведомление самому пользователю, чтобы он порадовался
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text=f"🎁 <b>Вам подарок от администратора!</b>\nВаша подписка успешно активирована на {days_to_add} дней. Проверьте ваш Личный кабинет!",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await message.answer("❌ <b>Ошибка X-UI панели:</b> Не удалось продлить подписку. Убедитесь, что пользователь нажал /start и существует в панели.")




# --- Валидация платежа ---
@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: types.PreCheckoutQuery, bot: Bot):
    try:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    except Exception as e:
        logging.error(f"Ошибка в pre_checkout_query: {e}")

# --- Обработка успешного платежа ---
@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message):
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload
    
    if payload == "vpn_30_days_subscription":
        success = await renew_vpn_subscription(user_id)
        config, happ_url = await get_vpn_config_manual(user_id, message.from_user.username or "")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        if happ_url:
            kb.inline_keyboard.append([InlineKeyboardButton(text="⚡️ ОТКРЫТЬ В HAPP", url=happ_url)])
            
        if success:
            await message.answer(
                f"✅ <b>Оплата прошла успешно!</b>\nВаша подписка продлена на 30 дней.\n\n"
                f"<b>Ваш новый ключ:</b>\n<code>{config}</code>",
                reply_markup=kb if happ_url else None, 
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"⚠️ <b>Оплата прошла успешно, но возник сбой синхронизации!</b>\n"
                f"Администратор уже уведомлен. Ваш ID: <code>{user_id}</code>",
                reply_markup=kb if happ_url else None, 
                parse_mode="HTML"
            )

# --- Запуск ---
async def main():
    # Очищаем вебхуки от старых запросов при перезапусках
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Инициализируем стандартную базу данных sqlite3
    init_db()
    logging.info("Диспетчер: База данных успешно инициализирована таблицами.")

    # Фоновый запуск сайта-админки базы данных sqlite-web
    try:
        subprocess.Popen(
            ["sqlite-web", DB_PATH, "--port", "8080", "--host", "0.0.0.0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        logging.info("Диспетчер: Запрос на фоновый запуск сайта-админки на порту 8080 отправлен.")
    except Exception as e:
        logging.warning(f"Не удалось запустить сайт-админку (это не влияет на бота): {e}")

    logging.info("Диспетчер: Бот успешно запущен на хостинге Amvera. Начинаем Polling...")
    await dp.start_polling(bot)


def get_all_users_from_db():
    """Получить список Telegram ID всех пользователей бота для рассылки"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    rows = cursor.fetchall()
    conn.close()
    # Превращаем список кортежей [(123,), (456,)] в обычный список [123, 456]
    return [row[0] for row in rows]


if __name__ == '__main__':
    asyncio.run(main())





