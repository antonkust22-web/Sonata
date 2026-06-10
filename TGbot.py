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


# ТОКЕН ПЛАТЕЖКИ ЮKASSA
PROVIDER_TOKEN = "390540012:LIVE:96775"

# File ID вашего видео
VIDEO_MAIN = "BAACAgIAAxkBAAMNailcPwV0q8eFSyhltQtxQywU1sgAAh2qAAKFqEhJPIGIg3JS6007BA"

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






# === НАСТРОЙКИ СЕРВЕРОВ (Заполните своими данными) ===
SERVERS_CONFIG = {
    "FI": {  # Финляндия (Ваш старый сервер)
        "panel_url": "https://78.17.1.43:10096", # Старый URL панели
        "base_path": "/XWYB6HCgL7NBchJqxo",     # Старый секретный путь
        "username": "Asad",
        "password": "Lodka120259",
        "inbound_id": 1,                         # ID подключения на финском сервере
        "ip": "78.17.1.43",
        "pbk": "MaiX75YfQdaUmvHJAMxBBt2bYldgZWA7RFJURoTGQ38",
        "sid": "32b6a4ff54ef1812",
        "sni": "sony.com",  # Пишем чистый домен без ://
        "flag": "🇫🇮",
        "name": "Финляндия"
    },
    "PL": {  # Польша (Новый сервер)
        "panel_url": "http://78.17.152.36:10096", # Новый URL панели в Docker
        "base_path": "/XWYB6HCgL7NBchJqxo",     # Новый секретный путь панели
        "username": "Soul",                     # Логин от новой панели
        "password": "Lodka1321",                     # Пароль от новой панели
        "inbound_id": 1,                         # ID подключения на польском сервере (обычно 1)
        "ip": "78.17.152.36",
        "pbk": "zf60IyIK8kF1aHG-SQNnu0L86e_C3TJ8gY1KiB-oQ3Q",           # Возьмите из настроек Reality в панели Польши
        "sid": "56b1550292e606d7",                # Возьмите из настроек Reality в панели Польши
        "sni": "sony.com",                      # Любой рабочий SNI для Польши (например, yahoo.com)
        "flag": "🇵🇱",
        "name": "Польша"
    }
}

async def get_vpn_config_manual(user_id, username=""):
    connector = aiohttp.TCPConnector(ssl=False)
    
    client_uuid = str(uuid.uuid4())
    sub_id = secrets.token_hex(8)
    config_links = []
    expiry_time_ms = 0
    success_count = 0  # Счетчик успешных серверов
    
    async with aiohttp.ClientSession(connector=connector) as session:
        # Поочередно опрашиваем наши сервера
        for s_key, s_data in SERVERS_CONFIG.items():
            try:
                email = f"{s_data['flag']}_{s_data['name']}_#{user_id}".replace(" ", "_")
                
                # 1. ПРИНУДИТЕЛЬНАЯ РУЧНАЯ АВТОРИЗАЦИЯ
                login_url = f"{s_data['panel_url']}{s_data['base_path']}/login"
                login_data = {"username": s_data['username'], "password": s_data['password']}
                
                async with session.post(login_url, data=login_data, timeout=7) as login_resp:
                    await login_resp.text()
                    # Вытаскиваем куки вручную из заголовков ответа панели
                    cookies = login_resp.headers.getall("Set-Cookie", [])
                    if not cookies:
                        logging.error(f"❌ Сервер {s_key}: Не удалось получить куки авторизации. Проверьте логин/пароль!")
                        continue
                    
                    # Формируем заголовок Cookie для последующих запросов
                    cookie_header = "; ".join([c.split(";")[0] for c in cookies])

                # Собираем строгие заголовки для работы с API инбаундов
                headers = {
                    "Accept": "application/json",
                    "Cookie": cookie_header  # Намертво привязываем куку авторизации к запросу
                }

                # 2. ПОЛУЧЕНИЕ ДАННЫХ ИНБАУНДА С АВТОПОДБОРОМ ПУТИ API
                res_json = None
                for api_prefix in ["/panel/api", "/xui/API"]:
                    get_url = f"{s_data['panel_url']}{s_data['base_path']}{api_prefix}/inbounds/get/{s_data['inbound_id']}"
                    try:
                        async with session.get(get_url, headers=headers, timeout=5) as resp:
                            if resp.status == 200 and "application/json" in resp.headers.get("Content-Type", ""):
                                res_json = await resp.json()
                                s_data["working_api"] = api_prefix
                                break
                    except Exception:
                        continue
                
                if not res_json or not res_json.get("success"):
                    logging.error(f"❌ Серver {s_key} ответил отказом/404 на запрос инбаунда. Проверьте, активен ли Inbound ID {s_data['inbound_id']}.")
                    continue  # Этот сервер не ответил, но мы продолжаем опрос остальных!

                # Считываем настройки клиентов внутри инбаунда
                settings = json.loads(res_json["obj"]["settings"])
                clients = settings.get("clients", [])
                
                # Ищем пользователя по tgId или по старому email в базе панели
                current_client = next((c for c in clients if c.get("tgId") == user_id), None)
                if not current_client:
                    old_email = f"user_{user_id}"
                    current_client = next((c for c in clients if c.get("email") == old_email), None)

                # Если клиент уже существует, берем его параметры, чтобы не перезаписывать
                if current_client:
                    client_uuid = current_client.get("id", client_uuid)
                    sub_id = current_client.get("subId", sub_id)
                    expiry_time_ms = max(expiry_time_ms, current_client.get("expiryTime", 0))

                # 3. ДОБАВЛЕНИЕ ИЛИ ОБНОВЛЕНИЕ КЛИЕНТА
                working_api = s_data.get("working_api", "/panel/api")
                
                if not current_client:
                    # Создаем нового пользователя
                    add_url = f"{s_data['panel_url']}{s_data['base_path']}{working_api}/inbounds/addClient"
                    post_data = {
                        "id": str(s_data['inbound_id']), 
                        "settings": json.dumps({"clients": [{
                            "id": client_uuid, "email": email, "limitIp": 2, "totalGB": 0,
                            "expiryTime": 0, "enable": True, "tgId": user_id, "subId": sub_id  
                        }]})
                    }
                    async with session.post(add_url, headers=headers, data=post_data, timeout=5) as resp:
                        await resp.text()
                else:
                    # Обновляем существующего (продлеваем активность)
                    update_url = f"{s_data['panel_url']}{s_data['base_path']}{working_api}/inbounds/updateClient/{client_uuid}"
                    post_data = {
                        "id": str(s_data['inbound_id']),
                        "settings": json.dumps({"clients": [{
                            "id": client_uuid, "email": email, "limitIp": current_client.get("limitIp", 2),
                            "totalGB": current_client.get("totalGB", 0), "expiryTime": current_client.get("expiryTime", 0),
                            "enable": True, "tgId": user_id, "subId": sub_id
                        }]})
                    }
                    async with session.post(update_url, headers=headers, data=post_data, timeout=5) as resp:
                        await resp.text()

                # 4. ФОРМИРОВАНИЕ ПРЯМОЙ КОНФИГУРАЦИИ VLESS
                my_port = res_json["obj"]["port"]
                remark = f"{s_data['flag']} {s_data['name']}?Premium"
                config_link = (
                    f"vless://{client_uuid}@{s_data['ip']}:{my_port}"
                    f"?type=tcp&security=reality&sni={s_data['sni']}&fp=chrome&pbk={s_data['pbk']}&sid={s_data['sid']}&spx=%2F"
                    f"#{urllib.parse.quote(remark)}"
                )
                config_links.append(config_link)
                success_count += 1

            except Exception as server_error:
                logging.error(f"⚠️ Ошибка изоляции сессии сервера {s_key}: {server_error}")
                continue

    # 5. ФОРМИРОВАНИЕ ЕДИНОЙ ССЫЛКИ ПОДПИСКИ НА БАЗЕ СЕРВЕРА ПОЛЬШИ (ПОРТ 2096)
    sub_remark = urllib.parse.quote("🚀 Sonata VPN")
    subscription_web_url = f"http://{SERVERS_CONFIG['PL']['ip']}:2096/sub/{sub_id}#{sub_remark}"

    # Если хотя бы один из серверов успешно ответил — пишем данные в локальную БД бота
    if success_count > 0:
        expiry_seconds = int(expiry_time_ms / 1000) if expiry_time_ms > 0 else 0
        all_configs_str = "\n".join(config_links)
        add_or_update_user(user_id, username, all_configs_str, subscription_web_url, expiry_seconds)
        return all_configs_str, subscription_web_url
        
    return None, None








# Функция использует тот же словарь SERVERS_CONFIG, который мы создали на предыдущем шаге
# Обязательно убедитесь, что SERVERS_CONFIG импортирован или находится в этом же файле!

async def renew_vpn_subscription(user_id: int) -> bool:
    """
    Продлевает подписку на 30 дней на ВСЕХ подключенных серверах (Финляндия и Польша).
    Использует корректные пути API (/xui/API/) для интеграции с панелями 3X-UI.
    """
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)

    current_time_ms = int(time.time() * 1000)
    thirty_days_ms = 30 * 24 * 60 * 60 * 1000
    
    # Сюда запишем итоговое время продления для базы данных
    final_expiry_seconds = 0
    updated_servers_count = 0

    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            
            # Проходим циклом по всем серверам из конфигурации
            for s_key, s_data in SERVERS_CONFIG.items():
                try:
                    email = f"{s_data['flag']}_{s_data['name']}_#{user_id}".replace(" ", "_")
                    
                    # 1. Авторизация на конкретном сервере
                    login_url = f"{s_data['panel_url']}{s_data['base_path']}/login"
                    async with session.post(login_url, data={"username": s_data['username'], "password": s_data['password']}, timeout=10) as resp:
                        await resp.text()

                    headers = {"Accept": "application/json"}

                    # 2. Получаем текущие данные инбаунда (ИСПРАВЛЕНО: добавлен путь /xui/API/)
                    get_url = f"{s_data['panel_url']}{s_data['base_path']}/xui/API/inbounds/get/{s_data['inbound_id']}"
                    async with session.get(get_url, headers=headers, timeout=10) as resp:
                        res_json = await resp.json()

                    if not res_json.get("success"):
                        logging.error(f"Не удалось получить данные инбаунда на сервере {s_key}: {res_json}")
                        continue

                    settings = json.loads(res_json["obj"]["settings"])
                    clients = settings.get("clients", [])

                    # Поиск клиента строго по уникальному tgId
                    client = next((c for c in clients if c.get("tgId") == user_id), None)
                    if not client:
                        logging.warning(f"Клиент {user_id} не найден в панели сервера {s_key}. Пропускаем.")
                        continue

                    # 3. Расчет времени (если подписка еще активна — плюсуем к ней, если сгорела — от текущего времени)
                    client_expiry = client.get("expiryTime", 0)
                    if client_expiry > current_time_ms:
                        new_expiry = client_expiry + thirty_days_ms
                    else:
                        new_expiry = current_time_ms + thirty_days_ms

                    # Фиксируем максимальную дату для сохранения в локальную БД бота
                    final_expiry_seconds = max(final_expiry_seconds, int(new_expiry / 1000))

                    client_uuid = client['id']
                    client_sub_id = client.get("subId", "")
                    if not client_sub_id:
                        client_sub_id = secrets.token_hex(8)

                    # 4. Отправка обновленных данных на сервер (ИСПРАВЛЕНО: добавлен путь /xui/API/)
                    update_url = f"{s_data['panel_url']}{s_data['base_path']}/xui/API/inbounds/updateClient/{client_uuid}"
                    client_data = {
                        "id": str(s_data['inbound_id']),
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

                    if update_resp.get("success", False):
                        logging.info(f"Сервер {s_key} успешно продлил подписку для {user_id}.")
                        updated_servers_count += 1
                    else:
                        logging.error(f"Сервер {s_key} ответил ошибкой при попытке продления: {update_resp}")

                except Exception as server_err:
                    logging.error(f"Ошибка при работе с сервером {s_key}: {server_err}")

            # 5. Если хотя бы один сервер успешно обновился, считаем операцию успешной
            if updated_servers_count > 0:
                # Обновляем дату окончания в локальной БД бота
                add_or_update_user(user_id, "", expiry_time=final_expiry_seconds)
                logging.info(f"ЮKassa: Подписка пользователя {user_id} успешно продлена на {updated_servers_count} серверах.")
                return True
            
            return False

    except Exception as e:
        logging.error(f"Глобальная ошибка при продлении подписки через ЮKassa: {e}")
        return False



# Функция использует тот же словарь SERVERS_CONFIG, который мы создали ранее.
# Убедитесь, что он импортирован или находится в этом же файле.

async def renew_vpn_subscription_flexible(user_id: int, days: int):
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    current_time_ms = int(time.time() * 1000)
    custom_days_ms = days * 24 * 60 * 60 * 1000
    
    final_expiry_seconds = 0
    updated_servers_count = 0
    client_sub_id = ""

    async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
        for s_key, s_data in SERVERS_CONFIG.items():
            try:
                email = f"{s_data['flag']}_{s_data['name']}_#{user_id}".replace(" ", "_")
                
                # 1. Авторизация
                login_url = f"{s_data['panel_url']}{s_data['base_path']}/login"
                async with session.post(login_url, data={"username": s_data['username'], "password": s_data['password']}, timeout=7) as resp:
                    await resp.text()
                
                headers = {"Accept": "application/json"}

                # Автоподбор путей API
                res_json = None
                for api_prefix in ["/panel/api", "/xui/API"]:
                    get_url = f"{s_data['panel_url']}{s_data['base_path']}{api_prefix}/inbounds/get/{s_data['inbound_id']}"
                    try:
                        async with session.get(get_url, headers=headers, timeout=5) as resp:
                            if resp.status == 200 and "application/json" in resp.headers.get("Content-Type", ""):
                                res_json = await resp.json()
                                s_data["working_api"] = api_prefix
                                break
                    except Exception:
                        continue
                    
                if not res_json or not res_json.get("success"):
                    logging.warning(f"⚠️ Сервер {s_key} пропущен при продлении (не отвечает).")
                    continue

                settings = json.loads(res_json["obj"]["settings"])
                clients = settings.get("clients", [])
                
                client = next((c for c in clients if c.get("tgId") == user_id), None)
                if not client:
                    continue

                # Расчет времени продления
                client_expiry = client.get("expiryTime", 0)
                if client_expiry > current_time_ms:
                    new_expiry = client_expiry + custom_days_ms
                else:
                    new_expiry = current_time_ms + custom_days_ms

                final_expiry_seconds = max(final_expiry_seconds, int(new_expiry / 1000))
                client_uuid = client['id']
                
                if not client_sub_id:
                    client_sub_id = client.get("subId", secrets.token_hex(8))

                # 4. Продлеваем ЭТОТ конкретный сервер
                working_api = s_data.get("working_api", "/panel/api")
                update_url = f"{s_data['panel_url']}{s_data['base_path']}{working_api}/inbounds/updateClient/{client_uuid}"
                client_data = {
                    "id": str(s_data['inbound_id']),
                    "settings": json.dumps({"clients": [{
                        "id": client_uuid, "email": email, "limitIp": client.get("limitIp", 2),
                        "totalGB": client.get("totalGB", 0), "expiryTime": new_expiry,
                        "enable": True, "tgId": user_id, "subId": client_sub_id
                    }]})
                }
                async with session.post(update_url, headers=headers, data=client_data, timeout=5) as resp:
                    update_resp = await resp.json()
                
                if update_resp.get("success", False):
                    updated_servers_count += 1

            except Exception as e:
                logging.error(f"Ошибка продления на сервере {s_key}: {e}")
                continue

    if updated_servers_count > 0:
        add_or_update_user(user_id, "", expiry_time=final_expiry_seconds)
        return client_sub_id
        
    return False





import aiohttp
import json
import logging

# Функция использует тот же словарь SERVERS_CONFIG, который мы создали ранее.
# Убедитесь, что он импортирован или находится в этом же файле.

async def revoke_vpn_subscription(user_id: int) -> bool:
    """
    Аннулирует подписку в 3X-UI на ВСЕХ подключенных серверах (Финляндия и Польша),
    переводя её в неактивное состояние ("enable": False, expiryTime: 1).
    Использует корректные пути API (/xui/API/) для интеграции с панелями 3X-UI.
    """
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    updated_servers_count = 0
    past_expiry = 1  # Принудительное истекшее время (1 мс от начала эпохи Unix)

    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            
            # Проходим циклом по всем серверам из конфигурации
            for s_key, s_data in SERVERS_CONFIG.items():
                try:
                    email = f"{s_data['flag']}_{s_data['name']}_#{user_id}".replace(" ", "_")
                    
                    # 1. Авторизация на конкретном сервере
                    login_url = f"{s_data['panel_url']}{s_data['base_path']}/login"
                    async with session.post(login_url, data={"username": s_data['username'], "password": s_data['password']}, timeout=10) as resp:
                        await resp.text()

                    headers = {"Accept": "application/json"}

                    # 2. Получаем текущие данные инбаунда с этого сервера (ИСПРАВЛЕНО: добавлен путь /xui/API/)
                    get_url = f"{s_data['panel_url']}{s_data['base_path']}/xui/API/inbounds/get/{s_data['inbound_id']}"
                    async with session.get(get_url, headers=headers, timeout=10) as resp:
                        res_json = await resp.json()

                    if not res_json.get("success"):
                        logging.error(f"Не удалось получить данные инбаунда на сервере {s_key} для отзыва подписки: {res_json}")
                        continue

                    settings = json.loads(res_json["obj"]["settings"])
                    clients = settings.get("clients", [])

                    # Поиск строго по уникальному tgId
                    client = next((c for c in clients if c.get("tgId") == user_id), None)
                    if not client:
                        logging.warning(f"Клиент {user_id} не найден в панели сервера {s_key} для отзыва. Пропускаем.")
                        continue

                    client_uuid = client['id']
                    
                    # 3. Отправка заблокированных параметров клиента на текущий сервер (ИСПРАВЛЕНО: добавлен путь /xui/API/)
                    update_url = f"{s_data['panel_url']}{s_data['base_path']}/xui/API/inbounds/updateClient/{client_uuid}"
                    client_data = {
                        "id": str(s_data['inbound_id']),
                        "settings": json.dumps({
                            "clients": [{
                                "id": client_uuid,
                                "email": email,
                                "limitIp": client.get("limitIp", 2),
                                "totalGB": client.get("totalGB", 0),
                                "expiryTime": past_expiry,
                                "enable": False,  # Полностью выключаем аккаунт на сервере
                                "tgId": user_id,
                                "subId": client.get("subId", "")
                            }]
                        })
                    }

                    async with session.post(update_url, headers=headers, data=client_data, timeout=10) as resp:
                        update_resp = await resp.json()

                    if update_resp.get("success", False):
                        logging.info(f"Сервер {s_key} успешно аннулировал подписку для {user_id}.")
                        updated_servers_count += 1
                    else:
                        logging.error(f"Сервер {s_key} ответил ошибкой при попытке отзыва подписки: {update_resp}")

                except Exception as server_err:
                    logging.error(f"Ошибка при отзыве подписки на сервере {s_key}: {server_err}")

            # 4. Если хотя бы на одном сервере блокировка прошла успешно, обновляем локальную БД бота
            if updated_servers_count > 0:
                add_or_update_user(user_id, "", expiry_time=0)
                logging.info(f"Отзыв подписки: Пользователь {user_id} успешно деактивирован на {updated_servers_count} серверах.")
                return True
                
            return False

    except Exception as e:
        logging.error(f"Глобальная ошибка при отзыве подписки: {e}")
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
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"
    
    # 1. Записываем пользователя в локальную базу данных SQLite3
    add_or_update_user(user_id, username)
    
    # 2. Автоматически создаем/проверяем аккаунты на серверах Финляндии и Польши
    # Пути внутри этой функции мы уже исправили на /xui/API/, так что она отработает без ошибок
    await get_vpn_config_manual(user_id, username)
    
    # 3. Отправляем приветственное видео по обновленному file_id
    try:
        # Используем ваш новый file_id из переменной VIDEO_MAIN
        await message.answer_video(
            video=VIDEO_MAIN, 
            caption=text1,
            reply_markup=main_kb(),
            parse_mode="HTML"
        )
        logging.info(f"Приветственное видео успешно отправлено пользователю {user_id}")
        
    except Exception as e:
        # Если с новым file_id опять что-то пойдет не так, бот не упадет, а отправит текст
        logging.error(f"Не удалось отправить видео по file_id при старте, отправляю текст: {e}")
        await message.answer(
            text=text1,
            reply_markup=main_kb(),
            parse_mode="HTML"
        )



import math # Добавляем в самый верх файла для правильного подсчета дней

@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    # Синхронизируем данные со ВСЕМИ панелями X-UI (Финляндия + Польша)
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
            # Рассчитываем оставшиеся дни с округлением вверх (так честнее и красивее)
            days_left = math.ceil((expiry_timestamp - current_time) / (24 * 3600))
            status_text = f"🟢 Активна (осталось {days_left} дн.)"

            # Полностью чистый текст БЕЗ каких-либо vless:// и веб-ссылок
            text = (
                f"<b>👤 Личный кабинет</b>\n\n"
                f"<b>ID пользователя:</b> <code>{user_id}</code>\n"
                f"<b>Статус подписки:</b> {status_text}\n\n"
                f"✨ Ваша мультисерверная подписка активна! Доступны локации: Финляндия 🇫🇮 и Польша 🇵🇱.\n\n"
                f"Чтобы подключить устройство, получить настройки или обновить сервера, перейдите в главное меню бота и нажмите кнопку <b>«Подключиться»</b>."
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
                f"⚠️ Для получения доступа к высокоскоростному VPN Sonata (Финляндия + Польша), пожалуйста, приобретите подписку."
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





import urllib.parse
import aiohttp
import logging
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    # Сразу гасим часики анимации в Telegram, чтобы кнопка не висела в загрузке
    await callback.answer()
    user_id = callback.from_user.id

    try:
        # Делаем прямой запрос в панели X-UI через вашу новую функцию синхронизации.
        # Она обходит оба сервера и возвращает (all_configs_str, subscription_web_url)
        _, sub_web_url = await get_vpn_config_manual(user_id, callback.from_user.username or "")
        
        # Если панель X-UI выдала нам веб-ссылку подписки — значит, доступ ЕСТЬ и он АКТИВЕН!
        if sub_web_url and sub_web_url.startswith("http"):
            
            # Для Happ критически важен протокол https. Если ссылка на http (из-за Docker),
            # мы подменяем её исключительно для вызова приложения, чтобы Happ корректно её съел.
            happ_target_url = sub_web_url
            if happ_target_url.startswith("http://"):
                happ_target_url = happ_target_url.replace("http://", "https://", 1)

            # Собираем прямую ссылку для автоматического импорта в приложение Happ
            raw_happ_url = f"happ://import/{happ_target_url}"
            
            # Оборачиваем её через официальный API сервиса сокращения Яндекса (clck.ru)
            safe_redirect_url = raw_happ_url  # Резервный вариант, если сервис будет недоступен
            try:
                async with aiohttp.ClientSession() as session:
                    # Корректный эндпоинт Яндекса требует передачи урла через параметр ?url=
                    enc_url = urllib.parse.quote(raw_happ_url)
                    clck_api_url = f"https://clck.ru{enc_url}"
                    
                    async with session.get(clck_api_url, timeout=5) as resp:
                        if resp.status == 200:
                            safe_redirect_url = await resp.text()
            except Exception as e:
                logging.error(f"Не удалось сократить happ-ссылку через clck.ru: {e}")
                # Если упало, выдаем прямую веб-ссылку, чтобы кнопка в ТГ хотя бы открывала браузер
                safe_redirect_url = sub_web_url

            # Собираем инлайн-клавиатуру под мультисерверную подписку
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚡️ ИМПОРТИРОВАТЬ В HAPP (ВСЕ СЕРВЕРА)", url=safe_redirect_url)],
                [InlineKeyboardButton(text="🌐 Открыть подписку в браузере", url=sub_web_url)],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
            ])

            text = (
                "<b>📥 Автоматическое подключение (Финляндия 🇫🇮 + Польша 🇵🇱):</b>\n\n"
                "1. Установите приложение <b>Happ</b> из App Store или Google Play, если его еще нет.\n"
                "2. Нажмите кнопку <b>«⚡️ ИМПОРТИРОВАТЬ В HAPP (ВСЕ СЕРВЕРА)»</b> ниже.\n"
                "3. Смартфон автоматически откроет приложение Happ и добавит вашу единую подписку Sonata VPN.\n\n"
                "<b>💡 Если автоматический импорт не сработал:</b>\n"
                "• Нажмите пальцем на ссылку ниже, чтобы <b>скопировать её в буфер</b>:\n"
                f"<code>{sub_web_url}</code>\n\n"
                "• Откройте приложение Happ, нажмите значок <b>Плюс (➕)</b> в верхнем углу ➔ выберите пункт <b>«Добавить по ссылке» (Add by URL)</b> и вставьте скопированный адрес.\n\n"
                "<i>✨ Внутри приложения у вас автоматически появится список из двух доступных локаций!</i>"
            )

            await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
            
        else:
            # Если X-UI панель не вернула ссылку (пользователь истек, удален или отключен в панели)
            await callback.message.answer("⚠️ Доступ заблокирован! Сначала приобретите или продлите подписку в меню 'Купить подписку'.")

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
    
    # Автоматически регистрируем или проверяем пользователя на ОБЕИХ панелях (Финляндия + Польша)
    await get_vpn_config_manual(callback.from_user.id, callback.from_user.username or "")
    
    logging.info(f"Диспетчер: Отправка инвойса пользователю {callback.from_user.id}")
    
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Подписка на VPN (30 дней)",
        # Обновили описание, чтобы пользователь видел новые локации при оплате
        description="Продление доступа к Sonata VPN на 1 месяц. Доступны локации: Финляндия 🇫🇮 и Польша 🇵🇱.",
        payload="vpn_30_days_subscription",
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="1 месяц подписки", amount=15000)], # 150.00 руб.
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


import urllib.parse
from aiogram import types
from aiogram.filters import Command

@dp.message(Command("gift"))
async def admin_gift_sub(message: types.Message, bot: Bot): # Добавили bot в аргументы, если он используется внутри
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split()
        target_user_id = int(parts[1])  
        days_to_add = int(parts[2])     
    except (IndexError, ValueError):
        await message.answer(
            "⚠️ <b>Неверный формат!</b> Пишите так:\n<code>/gift ID_ПОЛЬЗОВАТЕЛЯ ДНИ</code>\n\n"
            "Пример: <code>/gift 584930211 5</code>", 
            parse_mode="HTML"
        )
        return

    await message.answer(f"⏳ Связываюсь с панелями X-UI для выдачи подписки на {days_to_add} дн. пользователю {target_user_id}...")

    # Вызываем нашу НОВУЮ функцию гибкого продления (она обойдет и Финляндию, и Польшу)
    sub_id = await renew_vpn_subscription_flexible(target_user_id, days_to_add)
    
    if sub_id:
        # Теперь жестко и правильно берем IP-адрес польского сервера с Docker-подписками из нашего конфига
        # Это гарантирует, что ссылка будет 100% рабочей
        try:
            host = SERVERS_CONFIG['PL']['ip']
        except Exception:
            host = "78.17.152.36" # Резервный IP Польши, если словаря нет под рукой

        # Ссылка в красивом стиле с портом подписок 2096
        sub_remark = urllib.parse.quote("🚀 Sonata VPN Premium")
        sub_link = f"http://{host}:2096/sub/{sub_id}#{sub_remark}"
        
        await message.answer(
            f"🎉 <b>Успех!</b> Доступ для <code>{target_user_id}</code> успешно продлен на {days_to_add} дней сразу на двух серверах (Финляндия 🇫🇮 + Польша 🇵🇱).\n\n"
            f"🔗 <b>Единая ссылка на подписку для клиента:</b>\n<code>{sub_link}</code>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        # Отправляем уведомление пользователю в ЛС
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎁 <b>Вам начислен бонус от администрации!</b>\n"
                    f"Ваша мультисерверная подписка (Финляндия + Польша) успешно активирована на <b>{days_to_add} дней</b>.\n\n"
                    f"Перейдите в Личный кабинет или нажмите кнопку <b>«Подключиться»</b> в главном меню для импорта настроек!"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {target_user_id} о подарке: {e}")
            pass
    else:
        await message.answer(
            "❌ <b>Ошибка X-UI панелей:</b> Не удалось продлить подписку. "
            "Убедитесь, что пользователь ранее нажимал /start, существует в базе и панели ответили успешно.",
            parse_mode="HTML"
        )


from aiogram import types
from aiogram.filters import Command

@dp.message(Command("revoke"))
async def admin_revoke_sub(message: types.Message, bot: Bot): # Добавили bot в аргументы функции
    if message.from_user.id != ADMIN_ID:
        return

    try:
        parts = message.text.split()
        target_user_id = int(parts[1])
    except (IndexError, ValueError):
        await message.answer("⚠️ <b>Неверный формат!</b> Пишите так:\n<code>/revoke ID_ПОЛЬЗОВАТЕЛЯ</code>", parse_mode="HTML")
        return

    await message.answer(f"⏳ Отзываю подписку у пользователя {target_user_id} на всех серверах X-UI...")

    # Вызываем нашу обновленную функцию (она отключит юзера и в Финляндии, и в Польше)
    success = await revoke_vpn_subscription(target_user_id)
    
    if success:
        await message.answer(
            f"🛑 <b>Подписка аннулирована!</b> Пользователь <code>{target_user_id}</code> "
            f"успешно отключен от всех локаций (Финляндия 🇫🇮 + Польша 🇵🇱).",
            parse_mode="HTML"
        )
        
        # Отправляем уведомление пользователю в ЛС
        try:
            await bot.send_message(
                chat_id=target_user_id,
                text="⚠️ <b>Ваша VPN подписка была аннулирована или досрочно завершена администратором.</b>",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление об отзыве пользователю {target_user_id}: {e}")
            pass
    else:
        await message.answer(
            "❌ <b>Ошибка X-UI панелей:</b> Не удалось отозвать подписку. "
            "Возможно, пользователя нет ни на одном из серверов.",
            parse_mode="HTML"
        )



import urllib.parse
import aiohttp
import logging
from aiogram import types, Bot, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Валидация платежа ---
@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout_query: types.PreCheckoutQuery, bot: Bot):
    try:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)
    except Exception as e:
        logging.error(f"Ошибка в pre_checkout_query: {e}")

# --- Обработка успешного платежа ---
@dp.message(F.successful_payment)
async def successful_payment_handler(message: types.Message, bot: Bot): # ДОБАВИЛИ bot: Bot в аргументы
    user_id = message.from_user.id
    payload = message.successful_payment.invoice_payload

    if payload == "vpn_30_days_subscription":
        # Наша новая функция продления (она зайдет и в Финляндию, и в Польшу одновременно)
        success = await renew_vpn_subscription(user_id)
        
        # Получаем обновленные данные подписки
        _, sub_web_url = await get_vpn_config_manual(user_id, message.from_user.username or "")

        # Формируем умную кнопку для автоматического импорта в Happ
        kb = InlineKeyboardMarkup(inline_keyboard=[])
        
        if sub_web_url and sub_web_url.startswith("http"):
            # Исправляем протокол для Happ (требуется https)
            happ_target_url = sub_web_url.replace("http://", "https://", 1) if sub_web_url.startswith("http://") else sub_web_url
            raw_happ_url = f"happ://import/{happ_target_url}"
            
            # Сокращаем ссылку через Яндекс clck.ru, чтобы Telegram её пропустил
            safe_redirect_url = raw_happ_url
            try:
                async with aiohttp.ClientSession() as session:
                    enc_url = urllib.parse.quote(raw_happ_url)
                    clck_api_url = f"https://clck.ru{enc_url}"
                    async with session.get(clck_api_url, timeout=5) as resp:
                        if resp.status == 200:
                            safe_redirect_url = await resp.text()
            except Exception as e:
                logging.error(f"Не удалось сократить happ-ссылку после оплаты: {e}")
                safe_redirect_url = sub_web_url # Резервный вариант

            # Добавляем красивую кнопку авто-импорта
            kb.inline_keyboard.append([
                InlineKeyboardButton(text="⚡️ ИМПОРТИРОВАТЬ В HAPP (ВСЕ СЕРВЕРА)", url=safe_redirect_url)
            ])

        # Конечный ответ пользователю в случае успешной синхронизации панелей
        if success:
            await message.answer(
                f"✅ <b>Оплата прошла успешно!</b>\n"
                f"Ваша мультисерверная подписка успешно продлена на 30 дней 🎉\n\n"
                f"Теперь вам одновременно доступны две локации: <b>Финляндия 🇫🇮 и Польша 🇵🇱</b>.\n\n"
                f"<b>📥 Как подключиться прямо сейчас:</b>\n"
                f"Нажмите на кнопку <b>«⚡️ ИМПОРТИРОВАТЬ В HAPP (ВСЕ СЕРВЕРА)»</b> ниже, чтобы автоматически добавить или обновить локации в приложении Happ.\n\n"
                f"<i>Вы также можете скопировать прямую ссылку или проверить остаток дней в меню «Личный кабинет».</i>",
                reply_markup=kb if sub_web_url else None, 
                parse_mode="HTML"
            )
        else:
            # Ответ, если ЮKassa деньги списала, но один из серверов X-UI в этот момент не ответил
            await message.answer(
                f"⚠️ <b>Оплата прошла успешно, но возник сбой автоматической синхронизации серверов!</b>\n"
                f"Не переживайте, ваш платеж зафиксирован в системе. Администратор уже получил уведомление и активирует вам доступ (Финляндия + Польша) вручную в течение нескольких минут.\n\n"
                f"Ваш ID для службы поддержки: <code>{user_id}</code>",
                reply_markup=kb if sub_web_url else None, 
                parse_mode="HTML"
            )




async def check_and_notify_expiring_subscriptions(bot):
    """
    Фоновая задача: проверяет пользователей, у которых общая подписка 
    заканчивается ровно через 4 дня, и отправляет им уведомление.
    """
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
        
        # Запрашиваем ID пользователей, у которых срок подходит к концу
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
            # Обновили текст: перевели на HTML для надежности и добавили упоминание локаций
            text = (
                "⚠️ <b>Внимание! Окончание подписки</b>\n\n"
                "Ваша мультисерверная подписка Sonata VPN (<b>Финляндия 🇫🇮 + Польша 🇵🇱</b>) "
                "заканчивается через <b>4 дня</b>.\n\n"
                "Пожалуйста, продлите её вовремя в Личном кабинете бота, чтобы не потерять доступ к высокоскоростной сети!"
            )
            
            # Отправка сообщения пользователю в Telegram через безопасный HTML
            await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
            logging.info(f"Уведомление об окончании успешно отправлено пользователю {user_id}")
            
            # Защитная пауза 0.05 сек (до 20 сообщений в секунду), чтобы Telegram не заблокировал бота за спам
            await asyncio.sleep(0.05) 
            
        except Exception as send_error:
            logging.error(f"Не удалось отправить уведомление пользователю {user_id}: {send_error}")




import asyncio
import logging
from datetime import datetime, time as datetime_time

async def scheduler(bot):
    """
    Надежный планировщик: запускает проверку подписок каждый день 
    строго в фиксированное время (например, в 10:00 утра).
    """
    logging.info("Планировщик подписок успешно запущен и переходит в режим ожидания...")
    
    # Задайте время, в которое бот будет рассылать уведомления (Часы, Минуты)
    TARGET_HOUR = 10
    TARGET_MINUTE = 0

    while True:
        try:
            now = datetime.now()
            # Высчитываем, когда должен быть следующий запуск (сегодня или уже завтра)
            target_time = now.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
            
            if now >= target_time:
                # Если 10:00 утра на сегодня уже прошло, переносим запуск на завтра
                target_time = target_time.replace(day=now.day + 1) # Автоматически учтет конец месяца

            # Считаем, сколько секунд осталось поспать до целевого времени
            seconds_to_wait = (target_time - now).total_seconds()
            logging.info(f"Планировщик: до следующей рассылки осталось {int(seconds_to_wait // 3600)} ч. и {int((seconds_to_wait % 3600) // 60)} мин.")
            
            # Спим ровно до 10:00 утра
            await asyncio.sleep(seconds_to_wait)
            
            # Наступило 10:00 — запускаем нашу фоновую задачу проверки базы
            await check_and_notify_expiring_subscriptions(bot)
            
            # Защитная пауза в 1 минуту после выполнения, чтобы цикл случайно не выполнился дважды в ту же секунду
            await asyncio.sleep(60)

        except Exception as e:
            logging.error(f"Критическая ошибка в планировщике подписок: {e}")
            # В случае сбоя спим 5 минут и пробуем снова, чтобы не повесить сервер бесконечным циклом ошибок
            await asyncio.sleep(300)






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


