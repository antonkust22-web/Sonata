import asyncio
import logging
import json
import uuid
import time
import urllib.parse
import secrets
import os
import subprocess
import sqlite3  # Используем стандартный встроенный sqlite3
import base64

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
API_TOKEN = '8728088789:AAFZSnTY46Z2v2-5hk3Henv5JBSkHXi5avQ'





# ТОКЕН ПЛАТЕЖКИ ЮKASSA
PROVIDER_TOKEN = "390540012:LIVE:96775"

# File ID вашего видео
VIDEO_MAIN = "BAACAgIAAxkBAAPaajJjgN8IT8fYPWnU7aYj4rhAhmIAAr2iAAJQ7ZFJltrjNm3tHII8BA"

text1 = (
    "👋 <b>Обходите блокировки легко!</b>\n"
    " ✅ Невидим для DPI\n"
    " ✅ Работает в строгих сетях\n"
    " ✅ Подключение в один клик\n\n"
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


from fastapi import FastAPI, HTTPException, Response
import base64

# Если объект app уже создан в файле, эту строку писать не нужно:
app = FastAPI()

@app.get("/sub/{sub_id}")
async def get_subscription(sub_id: str):
    """
    Эндпоинт, который вызывает Happ. 
    Выдает конфигурации Финляндии и Польши в одном пакете.
    """
    # 1. Достаем запись пользователя из вашей БД по sub_id
    # ВАЖНО: Замените get_user_by_sub_id на вашу реальную функцию работы с БД!
    user_data = get_user_by_sub_id(sub_id) 
    
    if not user_data:
        raise HTTPException(status_code=404, detail="Subscription not found")
        
    # В user_data["config_link"] должна лежать строка, сохраненная функцией add_or_update_user
    # Она содержит: "vless://...Финляндия...\nvless://...Польша..."
    configs_string = user_data.get("config_link", "")
    
    if not configs_string:
        raise HTTPException(status_code=404, detail="Configs are empty")
    
    # 2. Кодируем список серверов в формат Base64 (обязательно для Happ)
    base64_encoded_configs = base64.b64encode(configs_string.encode("utf-8")).decode("utf-8")
    
    # 3. Отдаем ответ клиенту Happ
    return Response(
        content=base64_encoded_configs,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Subscription-Userinfo": "upload=0; download=0; total=0; expire=0"
        }
    )



# Ваши актуальные данные серверов
SERVERS = [
    {
        "id": "fi_1",
        "panel_url": "https://78.17.1.43:2053",
        "base_path": "/bqPVI4YlUguDhw0MvD", 
        "panel_user": "Asad",
        "panel_password": "Lodka120259",
        "inbound_id": 1,
        "my_ip": "78.17.1.43",
        "pbk": "aZDw05rr-XfdquuaFADqMzM1aAdeFhhpx_Du69Io3Sc",
        "sid": "f2cfb510fbaa",
        "sni": "://sony.com",
        "country_flag": "🇫🇮",
        "country_name": "Финляндия"
    },
    {
        "id": "de_1",
        "panel_url": "http://78.17.152.36:2053",
        "base_path": "/root",
        "panel_user": "Soul",
        "panel_password": "Lodka1321",
        "inbound_id": 1,
        "my_ip": "78.17.152.36",
        "pbk": "XAAgoWsZcO3CWrMnx1r-hFNYVn8u5rfuZxCD-r5jKEY",
        "sid": "aa72b4f659",
        "sni": "://sony.com",
        "country_flag": "🇵🇱",
        "country_name": "Польша"
    }
]


async def get_vpn_config_manual(user_id, username=""):
    """
    Регистрирует/обновляет клиента на всех серверах X-UI.
    Формирует единую подписку. Перебирает API эндпоинты для обхода 404.
    """
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    config_links = []
    sub_id = secrets.token_hex(8) 
    expiry_time_ms = 0

    async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
        for srv in SERVERS:
            try:
                email = f"{srv['country_flag']}_{srv['country_name']}_#{user_id}".replace(" ", "_")
                
                # 1. Авторизация в панели
                login_url = f"{srv['panel_url']}{srv['base_path']}/login"
                await session.post(login_url, data={"username": srv['panel_user'], "password": srv['panel_password']}, timeout=5)

                headers = {"Accept": "application/json"}
                res_json = None

                # 2. Умный перебор путей API для предотвращения 404 ошибок
                # Пробуем последовательно 3 варианта путей, которые используются в разных версиях 3X-UI
                possible_urls = [
                    f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/get/{srv['inbound_id']}",
                    f"{srv['panel_url']}/panel/api/inbounds/get/{srv['inbound_id']}",
                    f"{srv['panel_url']}{srv['base_path']}/xui/API/inbounds/get/{srv['inbound_id']}"
                ]

                for url_option in possible_urls:
                    try:
                        async with session.get(url_option, headers=headers, timeout=4) as resp:
                            if resp.status == 200:
                                text_data = await resp.text()
                                # Проверяем, что вернулся именно валидный JSON, а не HTML-страница ошибки
                                if text_data.strip().startswith("{"):
                                    res_json = json.loads(text_data)
                                    if res_json.get("success"):
                                        break  # Успешно нашли рабочий эндпоинт API
                    except Exception:
                        continue

                if not res_json or not res_json.get("success"):
                    logging.error(f"Панель {srv['country_name']} отклонила все варианты API-путей. Проверьте ID инбаунда или версию панели.")
                    continue

                settings = json.loads(res_json["obj"]["settings"])
                clients = settings.get("clients", [])
                
                current_client = next((c for c in clients if c.get("tgId") == user_id), None)
                if not current_client:
                    old_email = f"user_{user_id}"
                    current_client = next((c for c in clients if c.get("email") == old_email), None)

                client_uuid = current_client.get("id") if current_client else str(uuid.uuid4())
                expiry_time_ms = current_client.get("expiryTime", 0) if current_client else 0
                
                if current_client and current_client.get("subId"):
                    sub_id = current_client.get("subId")

                # 3. Добавление или обновление на сервере
                if not current_client:
                    action_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/addClient"
                else:
                    action_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/updateClient/{client_uuid}"

                client_payload = {
                    "id": str(srv['inbound_id']),
                    "settings": json.dumps({
                        "clients": [{
                            "id": client_uuid,
                            "email": email,
                            "limitIp": 2,
                            "totalGB": 0,
                            "expiryTime": expiry_time_ms,
                            "enable": True,
                            "tgId": user_id,
                            "subId": sub_id
                        }]
                    })
                }
                
                # Дополнительно страхуем отправку на случай альтернативного пути для add/update
                async with session.post(action_url, headers=headers, data=client_payload, timeout=5) as resp:
                    if resp.status == 404 and srv["id"] == "de_1":
                        alt_action_url = f"{srv['panel_url']}/panel/api/inbounds/addClient" if not current_client else f"{srv['panel_url']}/panel/api/inbounds/updateClient/{client_uuid}"
                        async with session.post(alt_action_url, headers=headers, data=client_payload, timeout=5) as alt_resp:
                            await alt_resp.text()
                    else:
                        await resp.text()

                # 4. Сборка ссылки конфигурации vless://
                my_port = res_json["obj"]["port"]
                remark = f"{srv['country_flag']} {srv['country_name']} | Premium"
                safe_remark = urllib.parse.quote(remark)
                clean_sni = srv['sni'].replace("://", "")

                vless_link = (
                    f"vless://{client_uuid}@{srv['my_ip']}:{my_port}"
                    f"?type=tcp&security=reality&sni={clean_sni}&fp=chrome"
                    f"&pbk={srv['pbk']}&sid={srv['sid']}&spx=%2F"
                    f"#{safe_remark}"
                )
                config_links.append(vless_link)

            except Exception as e:
                logging.error(f"Не удалось обработать сервер {srv['country_name']}: {e}")

    if not config_links:
        return None, None

    all_configs_str = "\n".join(config_links)
    
    # Формируем чистую ссылку без дублирования протоколов для Happ
    sub_remark = urllib.parse.quote("🚀 Sonata VPN Premium")
    subscription_web_url = f"https://78.17.1{sub_id}#{sub_remark}"

    expiry_seconds = int(expiry_time_ms / 1000) if expiry_time_ms > 0 else 0
    add_or_update_user(user_id, username, all_configs_str, subscription_web_url, expiry_seconds)
    
    return all_configs_str, subscription_web_url






async def renew_vpn_subscription(user_id: int) -> bool:
    """
    Стандартная функция продления на 30 дней для ЮKassa (поиск по tgId).
    """
    country_flag = "🇫🇮"
    country_name = "Финляндия"
    # Добавлено нижнее подчеркивание между флагом и страной для единого стиля
    email = f"{country_flag}_{country_name}_#{user_id}".replace(" ", "_")

    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)

    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            # 1. Авторизация в панели
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            async with session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10) as resp:
                await resp.text()

            headers = {"Accept": "application/json"}

            # 2. Получаем текущие данные инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            async with session.get(get_url, headers=headers, timeout=10) as resp:
                res_json = await resp.json()

            if not res_json.get("success"):
                logging.error(f"Не удалось получить данные инбаунда для продления подписки ЮKassa: {res_json}")
                return False

            settings = json.loads(res_json["obj"]["settings"])
            clients = settings.get("clients", [])

            # Поиск строго по уникальному tgId
            client = next((c for c in clients if c.get("tgId") == user_id), None)
            if not client:
                logging.error(f"Клиент с tgId {user_id} не найден в панели X-UI.")
                return False

            # 3. Расчет времени (30 дней)
            current_time_ms = int(time.time() * 1000)
            thirty_days_ms = 30 * 24 * 60 * 60 * 1000

            if client.get("expiryTime", 0) > current_time_ms:
                new_expiry = client["expiryTime"] + thirty_days_ms
            else:
                new_expiry = current_time_ms + thirty_days_ms

            client_uuid = client['id']
            update_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/updateClient/{client_uuid}"

            client_sub_id = client.get("subId", "")
            if not client_sub_id:
                client_sub_id = secrets.token_hex(8)

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
                        "subId": client_sub_id
                    }]
                })
            }

            async with session.post(update_url, headers=headers, data=client_data, timeout=10) as resp:
                update_resp = await resp.json()

            success = update_resp.get("success", False)
            if success:
                expiry_seconds = int(new_expiry / 1000)
                add_or_update_user(user_id, "", expiry_time=expiry_seconds)
                logging.info(f"Подписка для пользователя {user_id} через ЮKassa успешно продлена в X-UI.")
                
            return success

    except Exception as e:
        logging.error(f"Ошибка при продлении подписки через ЮKassa: {e}")
        return False





async def renew_vpn_subscription_flexible(user_id: int, days: int):
    """
    Продлевает подписку в 3X-UI на ТОЧНОЕ количество дней (поиск по tgId).
    """
    country_flag = "🇫🇮"
    country_name = "Финляндия"
    email = f"{country_flag}_{country_name}_#{user_id}".replace(" ", "_")

    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            # 1. Авторизация в панели
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            async with session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10) as resp:
                await resp.text()
            
            headers = {"Accept": "application/json"}

            # 2. Получаем текущие данные инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            async with session.get(get_url, headers=headers, timeout=10) as resp:
                res_json = await resp.json()
                
            if not res_json.get("success"):
                logging.error(f"Не удалось получить данные инбаунда для гибкого продления: {res_json}")
                return False
                
            settings = json.loads(res_json["obj"]["settings"])
            clients = settings.get("clients", [])
            
            # Поиск строго по уникальному tgId
            client = next((c for c in clients if c.get("tgId") == user_id), None)
            
            if not client:
                logging.error(f"Клиент с tgId {user_id} не найден в панели X-UI.")
                return False

            # 3. Динамический расчет времени
            current_time_ms = int(time.time() * 1000)
            custom_days_ms = days * 24 * 60 * 60 * 1000
            
            if client.get("expiryTime", 0) > current_time_ms:
                new_expiry = client["expiryTime"] + custom_days_ms
            else:
                new_expiry = current_time_ms + custom_days_ms

            client_uuid = client['id']
            update_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/updateClient/{client_uuid}"
            
            client_sub_id = client.get("subId", "")
            if not client_sub_id:
                client_sub_id = secrets.token_hex(8)

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
                        "subId": client_sub_id
                    }]
                })
            }
            async with session.post(update_url, headers=headers, data=client_data, timeout=10) as resp:
                update_resp = await resp.json()
            
            success = update_resp.get("success", False)
            if success:
                expiry_seconds = int(new_expiry / 1000)
                add_or_update_user(user_id, "", expiry_time=expiry_seconds)
                logging.info(f"Подписка для пользователя {user_id} успешно продлена на {days} дн. в X-UI.")
                return client_sub_id
                
            return False
    except Exception as e:
        logging.error(f"Ошибка при гибком продлении подписки: {e}")
        return False


async def revoke_vpn_subscription(user_id: int) -> bool:
    """
    Аннулирует подписку в 3X-UI, переводя её в неактивное состояние (поиск по tgId).
    """
    country_flag = "🇫🇮"
    country_name = "Финляндия"
    email = f"{country_flag}_{country_name}_#{user_id}".replace(" ", "_")

    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)

    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            # 1. Авторизация в панели
            login_url = f"{PANEL_URL}{BASE_PATH}/login"
            async with session.post(login_url, data={"username": PANEL_USER, "password": PANEL_PASSWORD}, timeout=10) as resp:
                await resp.text()

            headers = {"Accept": "application/json"}

            # 2. Получаем текущие данные инбаунда
            get_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/get/{INBOUND_ID}"
            async with session.get(get_url, headers=headers, timeout=10) as resp:
                res_json = await resp.json()

            if not res_json.get("success"):
                logging.error(f"Не удалось получить данные инбаунда для отзыва подписки: {res_json}")
                return False

            settings = json.loads(res_json["obj"]["settings"])
            clients = settings.get("clients", [])

            # Поиск строго по уникальному tgId
            client = next((c for c in clients if c.get("tgId") == user_id), None)
            if not client:
                logging.error(f"Клиент с tgId {user_id} не найден в панели X-UI.")
                return False

            client_uuid = client['id']
            update_url = f"{PANEL_URL}{BASE_PATH}/panel/api/inbounds/updateClient/{client_uuid}"
            past_expiry = 1

            client_data = {
                "id": str(INBOUND_ID),
                "settings": json.dumps({
                    "clients": [{
                        "id": client_uuid,
                        "email": email,
                        "limitIp": client.get("limitIp", 2),
                        "totalGB": client.get("totalGB", 0),
                        "expiryTime": past_expiry,
                        "enable": False,  # Выключаем активность
                        "tgId": user_id,
                        "subId": client.get("subId", "")
                    }]
                })
            }

            async with session.post(update_url, headers=headers, data=client_data, timeout=10) as resp:
                update_resp = await resp.json()

            success = update_resp.get("success", False)
            if success:
                add_or_update_user(user_id, "", expiry_time=0)
                logging.info(f"Подписка для пользователя {user_id} успешно отозвана.")
                
            return success

    except Exception as e:
        logging.error(f"Ошибка при отзыве подписки: {e}")
        return False









# --- Клавиатуры ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ)", callback_data="connect")],
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

    # Синхронизируем данные с панелью X-UI
    await get_vpn_config_manual(user_id, callback.from_user.username or "")

    # Читаем данные из локальной SQLite3
    db_data = get_user_from_db(user_id)

    # Создаем клавиатуру для ЛК
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    if db_data and len(db_data) > 3:  # Если запись существует в базе
        expiry_timestamp = db_data[3] # Получаем Unix-время окончания из БД
        current_time = time.time()

        # ПРОВЕРКА: Если подписка активна (время окончания больше текущего)
        if expiry_timestamp > current_time:
            # Рассчитываем оставшиеся дни
            days_left = int((expiry_timestamp - current_time) / (24 * 3600))
            status_text = f"🟢 Активна (осталось {days_left} дн.)"

            # Полностью чистый текст БЕЗ каких-либо vless:// и веб-ссылок
            text = (
                f"<b>👤 Личный кабинет</b>\n\n"
                f"<b>ID пользователя:</b> <code>{user_id}</code>\n"
                f"<b>Статус подписки:</b> {status_text}\n\n"
                f"✨ Ваша подписка активна! Чтобы подключить устройство или обновить настройки, перейдите в главное меню бота и нажмите кнопку <b>«Подключиться»</b>."
            )
            # Оставляем только кнопку Назад
            kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])

        else:
            # ЕСЛИ ПОДПИСКА НЕ ОПЛАЧЕНА ИЛИ ИСТЕКЛА
            status_text = "🔴 Не активна (требуется оплата)"
            text = (
                f"<b>👤 Личный кабинет</b>\n\n"
                f"<b>ID пользователя:</b> <code>{user_id}</code>\n"
                f"<b>Статус подписки:</b> {status_text}\n\n"
                f"⚠️ Для получения доступа к высокоскоростному VPN Sonata, пожалуйста, приобретите подписку."
            )
            # Добавляем кнопки покупки и возврата назад
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
    # Сразу гасим часики анимации в Telegram, чтобы кнопка не висела в загрузке
    await callback.answer()
    user_id = callback.from_user.id

    try:
        # Вызываем функцию генерации подписки (возвращает строки конфигураций и веб-ссылку)
        configs_str, sub_web_url = await get_vpn_config_manual(user_id, callback.from_user.username or "")
        
        # Если ссылка подписки успешно сгенерирована
        if sub_web_url and sub_web_url.startswith("http"):
            
            # 1. Формируем чистую ссылку для автоматического импорта в Happ
            clean_sub_url = sub_web_url.strip()
            raw_happ_url = f"happ://import/{clean_sub_url}"
            safe_redirect_url = raw_happ_url  # Резервный вариант, если clck.ru недоступен
            
            # 2. Безопасное кодирование и сокращение ссылки через Яндекс (clck.ru)
            try:
                async with aiohttp.ClientSession() as session:
                    # Параметр safe='' принудительно кодирует двоеточия и слэши, защищая хост от поломок
                    enc_url = urllib.parse.quote(raw_happ_url, safe='')
                    clck_url = f"https://clck.ru{enc_url}"
                    
                    async with session.get(clck_url, timeout=5) as resp:
                        if resp.status == 200:
                            res_text = await resp.text()
                            if "clck.ru" in res_text:
                                safe_redirect_url = res_text.strip()
            except Exception as e:
                logging.error(f"Не удалось сократить happ-ссылку: {e}")
                safe_redirect_url = raw_happ_url

            # Собираем инлайн-клавиатуру с валидными URL
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚡️ ИМПОРТИРОВАТЬ В HAPP", url=safe_redirect_url)],
                [InlineKeyboardButton(text="🌐 Открыть в браузере", url=clean_sub_url)],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
            ])

            text = (
                "<b>📥 Подключение через приложение Happ:</b>\n\n"
                "1. Установите приложение <b>Happ</b> из App Store или Google Play.\n"
                "2. Нажмите кнопку <b>«⚡️ ИМПОРТИРОВАТЬ В HAPP»</b> ниже.\n"
                "3. Смартфон автоматически предложит открыть приложение и импортировать вашу подписку Sonata.\n\n"
                "<b>💡 Если автоматический импорт не сработал:</b>\n"
                "• Нажмите пальцем на ссылку ниже, чтобы <b>скопировать её</b>:\n"
                f"<code>{clean_sub_url}</code>\n\n"
                "• Откройте приложение Happ, нажмите <b>Плюс (➕)</b> в правом верхнем углу ➔ выберите <b>«Добавить по ссылке» (Add by URL)</b> и вставьте скопированный адрес."
            )

            await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            
        else:
            # Если панели недоступны или вернули ошибку
            await callback.message.answer("⚠️ Не удалось сгенерировать подписку. Доступ заблокирован или сервера временно недоступны.")

    except Exception as e:
        logging.error(f"Критическая ошибка в обработчике connect: {e}")
        await callback.message.answer("⚠️ Произошла внутренняя ошибка бота. Пожалуйста, попробуйте позже.")



            






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

# --- АДМИН-ПАНЕЛЬ: РАССЫЛКА, ПОДАРКИ С ССЫЛКАМИ И ОТЗЫВ ---

@dp.message(Command("send"))
async def admin_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    text_to_send = message.text.replace("/send", "").strip()
    
    if not text_to_send:
        await message.answer("⚠️ <b>Ошибка:</b> Вы ввели пустую команду. Пишите так: <code>/send Ваш текст</code>")
        return

    all_users = get_all_users_from_db()
    await message.answer(f"⏳ <b>Начата рассылка</b> для {len(all_users)} пользователей...")
    
    success_count = 0
    for user_id in all_users:
        try:
            await bot.send_message(chat_id=user_id, text=text_to_send, parse_mode="HTML")
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ <b>Рассылка завершена успешно!</b>\nДоставлено сообщений: {success_count} из {len(all_users)}")


@dp.message(Command("gift"))
async def admin_gift_sub(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split()
        target_user_id = int(parts[1])  
        days_to_add = int(parts[2])     
    except (IndexError, ValueError):
        await message.answer("⚠️ <b>Неверный формат!</b> Пишите так:\n<code>/gift ID_ПОЛЬЗОВАТЕЛЯ ДНИ</code>\n\nПример: <code>/gift 584930211 5</code>")
        return

    await message.answer(f"⏳ Связываюсь с панелью X-UI для выдачи подписки на {days_to_add} дн. пользователю {target_user_id}...")

    # Вызываем функцию гибкого продления (она вернет строку subId при успехе)
    sub_id = await renew_vpn_subscription_flexible(target_user_id, days_to_add)
    
    if sub_id:
        await get_vpn_config_manual(target_user_id)
        
        # Динамически вытаскиваем IP вашей панели из PANEL_URL, но подставляем порт подписок 2096
        # Если у вас PANEL_URL имеет вид "http://78.17.1.43:2053", скрипт возьмет чистый IP и сделает нужную вам ссылку
        try:
            import urllib.parse
            parsed_url = urllib.parse.urlparse(PANEL_URL)
            host = parsed_url.hostname if parsed_url.hostname else parsed_url.path.split(':')[0]
        except Exception:
            host = "78.17.1.43" # Резервное значение на случай сбоя парсинга

        # Ссылка в красивом стиле с вашим портом 2096
        sub_link = f"https://{host}:2096/sub/{sub_id}"
        
        await message.answer(
            f"🎉 <b>Успех!</b> Доступ для <code>{target_user_id}</code> успешно продлен на {days_to_add} дней.\n\n"
            f"🔗 <b>Ссылка на подписку (с верхней плашкой):</b>\n<code>{sub_link}</code>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
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


@dp.message(Command("revoke"))
async def admin_revoke_sub(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split()
        target_user_id = int(parts[1])
    except (IndexError, ValueError):
        await message.answer("⚠️ <b>Неверный формат!</b> Пишите так:\n<code>/revoke ID_ПОЛЬЗОВАТЕЛЯ</code>")
        return

    await message.answer(f"⏳ Отзываю подписку у пользователя {target_user_id} в панели X-UI...")

    success = await revoke_vpn_subscription(target_user_id)
    
    if success:
        await message.answer(f"🛑 <b>Подписка аннулирована!</b> Пользователь <code>{target_user_id}</code> больше не имеет доступа к VPN.")
        
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text="⚠️ <b>Ваша VPN подписка была аннулирована или досрочно завершена администратором.</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await message.answer("❌ <b>Ошибка X-UI панели:</b> Не удалось отозвать подписку. Возможно, пользователя нет в панели.")



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
        # Вызываем вашу стандартную функцию продления на 30 дней для ЮKassa
        success = await renew_vpn_subscription(user_id)
        
        # Получаем обновленные данные (теперь во второй переменной возвращается чистый веб-URL подписки)
        _, sub_web_url = await get_vpn_config_manual(user_id, message.from_user.username or "")

        # Формируем клавиатуру под новый формат ссылки
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        if sub_web_url:
            kb.inline_keyboard.append([
                InlineKeyboardButton(text="🌐 ОТКРЫТЬ ПОДПИСКУ (HAPP)", url=sub_web_url)
            ])

        if success:
            await message.answer(
                f"✅ <b>Оплата прошла успешно!</b>\n"
                f"Ваша подписка успешно продлена на 30 дней 🎉\n\n"
                f"<b>📥 Как подключиться:</b>\n"
                f"Нажмите на кнопку <b>«🌐 ОТКРЫТЬ ПОДПИСКУ (HAPP)»</b> ниже, чтобы автоматически импортировать настройки или открыть веб-страницу вашей подписки со статистикой.\n\n"
                f"<i>Также вы в любой момент можете управлять вашим подключением через кнопку «Подключиться» в главном меню бота.</i>",
                reply_markup=kb if sub_web_url else None, 
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"⚠️ <b>Оплата прошла успешно, но возник сбой автоматической синхронизации!</b>\n"
                f"Не переживайте, платеж зафиксирован. Администратор уже уведомлен и активирует вам доступ вручную в ближайшее время.\n\n"
                f"Ваш ID для поддержки: <code>{user_id}</code>",
                reply_markup=kb if sub_web_url else None, 
                parse_mode="HTML"
            )




async def check_and_notify_expiring_subscriptions(bot):
    """Фоновая задача: проверяет пользователей, у которых подписка 
    заканчивается ровно через 4 дня, и отправляет им уведомление."""
    logging.info("Запуск проверки истекающих подписок...")
    
    FOUR_DAYS_SECONDS = 4 * 24 * 60 * 60
    ONE_HOUR = 60 * 60 
    
    current_time = int(time.time())
    target_time_min = current_time + FOUR_DAYS_SECONDS - ONE_HOUR
    target_time_max = current_time + FOUR_DAYS_SECONDS + ONE_HOUR

    try:
        # Подключение к вашей базе данных на хостинге Amvera
        conn = sqlite3.connect("/app/users.db") 
        cursor = conn.cursor()
        
        # Исправлено: вместо tg_id теперь запрашивается user_id
        cursor.execute(
            "SELECT user_id FROM users WHERE expiry_time >= ? AND expiry_time <= ?", 
            (target_time_min, target_time_max)
        )
        users_to_notify = cursor.fetchall()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка при чтении БД для уведомлений: {e}")
        return

    # Рассылка уведомлений найденным пользователям
    for row in users_to_notify:
        user_id = row[0]  # Безопасно извлекаем ID пользователя из кортежа SQLite
        try:
            text = (
                "⚠️ **Внимание!**\n\n"
                "Ваша VPN-подписка заканчивается через **4 дня**.\n"
                "Пожалуйста, продлите её вовремя, чтобы не потерять доступ к сети."
            )
            # Отправка сообщения пользователю в Telegram
            await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
            logging.info(f"Уведомление об окончании успешно отправлено пользователю {user_id}")
            
            # Защитная пауза 0.05 сек (до 20 сообщений в секунду), чтобы Telegram не заблокировал бота за спам
            await asyncio.sleep(0.05) 
            
        except Exception as send_error:
            logging.error(f"Не удалось отправить уведомление пользователю {user_id}: {send_error}")




async def scheduler(bot):
    """Цикл, который запускает проверку раз в сутки под именем scheduler."""
    # Даем боту 10 секунд на запуск
    await asyncio.sleep(10)
    
    while True:
        try:
            await check_and_notify_expiring_subscriptions(bot)
        except Exception as e:
            logging.error(f"Критическая ошибка в планировщике подписок: {e}")
        
        # Спим 24 часа до следующей проверки
        await asyncio.sleep(24 * 60 * 60)





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


    # 2. ЗАПУСК ПЛАНИРОВЩИКА (Сначала запускаем фоновую задачу)
    asyncio.create_task(scheduler(bot))
    logging.info("Фоновый планировщик успешно запущен")

    

    
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

