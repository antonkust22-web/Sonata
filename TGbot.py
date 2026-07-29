
import asyncio
import logging
import json
import uuid
import time
import urllib.parse
import secrets
import os
import base64
import zlib
import subprocess
import hashlib
import re
import sqlite3  
import datetime
import shutil

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, timedelta
from aiogram import types



# --- ПРАВА АДМИНИСТРАТОРА ---
ADMIN_ID = 8759913724  # ОБЯЗАТЕЛЬНО: Замените эти цифры на ваш настоящий Telegram ID




# --- НАСТРОЙКА ПУТИ К БД ДЛЯ ХОСТИНГА AMVERA ---
# Настройка пути к БД под хостинг Amvera
if os.path.exists("/data"):
    DB_PATH = "/data/users.db"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, "users.db")

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
# --- Настройки (ОБЯЗАТЕЛЬНО ОБНОВИТЕ ТОКЕН И ПАРОЛЬ) ---
API_TOKEN = '8728088789:AAFZSnTY46Z2v2-5hk3Henv5JBSkHXi5avQ'

# ТОКЕН ПЛАТЕЖКИ ЮKASSA
PROVIDER_TOKEN = "390540012:LIVE:96775"

# File ID вашего видео
VIDEO_MAIN = "BAACAgIAAxkBAAPqamn9mx0ZjN8O9LOXE_Nv1Vy8FHkAAo-qAAK3H1BL0SO5M78W3WA9BA"

text1 = (
    "<b>👋 Привет, добро пожаловать в наш VPN сервис</b>\n\n"
    " 🖥️ У нас доступны локации: Европейские страны, а также Белые Списки\n\n"
    "📖 Выберите действие:"
)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


#-----------Работа с базой данных----------------


# Путь к вашей базе данных (определен в вашем проекте)
# DB_PATH = "users.db"

def log_system_routing():
    """Выводит в логи информацию о путях БД при старте бота"""
    absolute_db_path = os.path.abspath(DB_PATH)
    logging.info("=" * 70)
    logging.info(f"⚙️  БАЗА ДАННЫХ УСПЕШНО ИНИЦИАЛИЗИРОВАНА ПО АДРЕСУ -> {absolute_db_path}")
    logging.info("=" * 70)

def init_db():
    logging.info(f"Диспетчер: Инициализация базы данных: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()

    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA synchronous=NORMAL;')

    # 1. Ваша существующая таблица пользователей (Порядок полей строго сохранен, role в конце)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            vpn_config TEXT,
            github_raw_url TEXT,
            expiry_time INTEGER DEFAULT 0,
            role TEXT DEFAULT 'user'  -- Новое поле добавлено в конец таблицы
        )
    ''')

    # 2. Обновленная таблица промокодов (Добавлено max_uses и current_uses)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            code TEXT PRIMARY KEY,
            days INTEGER NOT NULL,
            max_uses INTEGER DEFAULT 1,     -- 1 = одноразовый, 0 = без ограничений
            current_uses INTEGER DEFAULT 0  -- Сколько раз уже активировали всего
        )
    ''')
    
    # ТЕХНИЧЕСКИЙ ХАК ДЛЯ ПРОМОКОДОВ: Если таблица уже была на Amvera, добавляем новые колонки
    try:
        cursor.execute('ALTER TABLE promocodes ADD COLUMN max_uses INTEGER DEFAULT 1;')
        cursor.execute('ALTER TABLE promocodes ADD COLUMN current_uses INTEGER DEFAULT 0;')
    except sqlite3.OperationalError:
        pass 

    # ТЕХНИЧЕСКИЙ ХАК ДЛЯ ТАБЛИЦЫ USERS: Безопасно добавляем колонку role и новые счетчики действий в существующую структуру на сервере
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user';")
    except sqlite3.OperationalError:
        pass 

    try:
        # ВСТАВЛЕНО: Безопасное добавление колонок для подсчета админ-действий
        cursor.execute("ALTER TABLE users ADD COLUMN actions_gift INTEGER DEFAULT 0;")
        cursor.execute("ALTER TABLE users ADD COLUMN actions_gen INTEGER DEFAULT 0;")
    except sqlite3.OperationalError:
        pass # Если колонки уже есть, SQLite их просто пропустит

    # 3. Новая таблица для логирования активаций многоразовых промокодов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocode_activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            activated_at TEXT DEFAULT NULL,
            UNIQUE(code, user_id) -- Это жестко запретит одному юзеру вводить один код дважды
        )
    ''')


        # 4. Новая таблица для учета реферальных связей и построения ТОП-ов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referral_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER NOT NULL,  -- Кто пригласил (реферер)
            referral_id INTEGER NOT NULL, -- Кого пригласили (новый юзер)
            created_at TEXT DEFAULT (datetime('now', 'localtime')), -- Дата и время
            UNIQUE(referral_id) -- Один реферал может быть приглашен только один раз
        )
    ''')

    # ТЕХНИЧЕСКИЙ ХАК ДЛЯ СХЕМА-ИНДЕКСОВ [8] и: Добавляем поля для сохранения ОС и Приложения
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN saved_os TEXT DEFAULT NULL;")
        cursor.execute("ALTER TABLE users ADD COLUMN saved_app TEXT DEFAULT NULL;")
        logging.info("Диспетчер: Колонки saved_os и saved_app успешно проверены/добавлены.")
    except sqlite3.OperationalError:
        pass # Если колонки уже есть, SQLite их просто пропустит

    
    conn.commit()
    conn.close()
    log_system_routing()



def add_or_update_user(user_id, username, vpn_config=None, github_raw_url=None, expiry_time=None, role=None, saved_os=None, saved_app=None):
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    # Запрашиваем абсолютно ВСЕ 10 полей строго по порядку индексов от 0 до 9
    cursor.execute('''
        SELECT user_id, username, vpn_config, github_raw_url, expiry_time, 
               role, actions_gift, actions_gen, saved_os, saved_app 
        FROM users WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()

    # Защита: гарантируем, что expiry_time — это int перед записью
    clean_expiry = int(expiry_time) if expiry_time is not None else None

    if not row:
        cursor.execute('''
            INSERT INTO users (user_id, username, vpn_config, github_raw_url, expiry_time, role, actions_gift, actions_gen, saved_os, saved_app) 
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
        ''', (
                user_id, 
                username, 
                vpn_config, 
                github_raw_url, 
                clean_expiry if clean_expiry is not None else 0, 
                role if role is not None else 'user',
                saved_os,  # db[8]
                saved_app  # db[9]
            )
        )
    else:
        new_config = vpn_config if vpn_config is not None else row[2]
        new_github = github_raw_url if github_raw_url is not None else row[3]
        new_expiry = clean_expiry if clean_expiry is not None else row[4]
        new_role = role if role is not None else row[5]
        
        # Если новые значения ОС/Приложения не переданы в функцию, оставляем те, что уже лежали в БД
        new_os = saved_os if saved_os is not None else row[8]
        new_app = saved_app if saved_app is not None else row[9]

        try:
            new_expiry = int(new_expiry)
        except (ValueError, TypeError):
            new_expiry = 0

        cursor.execute('''
            UPDATE users SET 
                username = ?, 
                vpn_config = ?, 
                github_raw_url = ?, 
                expiry_time = ?, 
                role = ?,
                saved_os = ?,
                saved_app = ?
            WHERE user_id = ?
        ''', (username, new_config, new_github, new_expiry, new_role, new_os, new_app, user_id))
        
    conn.commit()
    conn.close()




def get_user_from_db(user_id):
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    # Строго соблюдаем структуру выдачи кортежа (tuple):
    # [0] = user_id
    # [1] = username
    # [2] = vpn_config
    # [3] = github_raw_url
    # [4] = expiry_time
    # [5] = role
    # [6] = actions_gift
    # [7] = actions_gen
    # [8] = saved_os   <- Новое поле устройства
    # [9] = saved_app  <- Новое поле сохраненного приложения
    cursor.execute('''
        SELECT user_id, username, vpn_config, github_raw_url, expiry_time, 
               role, actions_gift, actions_gen, saved_os, saved_app 
        FROM users WHERE user_id = ?
    ''', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row



def set_user_role(user_id, new_role):
    """Вспомогательная функция смены роли в БД, не задевающая остальные данные"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (new_role, user_id))
    conn.commit()
    conn.close()


def log_subscription_routing(user_id, username, sub_id, sub_url):
    """Логирует направление базы данных и сформированную ссылку"""
    absolute_db_path = os.path.abspath(DB_PATH)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    logging.info("-" * 80)
    logging.info(f"[{timestamp}] [МАРШРУТИЗАЦИЯ] Запрос подписки от @{username} (ID: {user_id})")
    logging.info(f"[{timestamp}] [БАЗА ДАННЫХ] Данные записаны в файл -> {absolute_db_path}")
    logging.info(f"[{timestamp}] [ТОКЕН] Сайт index.php заберет данные по токену: {sub_id}")
    logging.info(f"[{timestamp}] [ГОТОВАЯ ССЫЛКА] Ссылка для клиента -> {sub_url}")
    logging.info("-" * 80)






def generate_new_promocode(days: int, custom_code: str = None, max_uses: int = 1) -> str:
    """Генерирует промокод. max_uses=1 (для одного), max_uses=0 (многоразовый)"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    if not custom_code:
        random_part = secrets.token_hex(4).upper()
        code = f"SONATA-{random_part}"
    else:
        code = custom_code.strip().upper()
        
    try:
        cursor.execute(
            'INSERT INTO promocodes (code, days, max_uses, current_uses) VALUES (?, ?, ?, 0)',
            (code, days, max_uses)
        )
        conn.commit()
        return code
    except sqlite3.IntegrityError:
        return "EXISTS"
    finally:
        conn.close()



def activate_promo_in_db(code: str, user_id: int) -> str | int:
    """
    Проверяет промокод с учетом лимитов использования.
    Защищает от повторного ввода одним и тем же пользователем.
    """
    code = code.strip().upper()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    # 1. Ищем сам промокод
    cursor.execute('SELECT days, max_uses, current_uses FROM promocodes WHERE code = ?', (code,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return "NOT_FOUND"
        
    days, max_uses, current_uses = row
    
    # 2. Проверяем, не активировал ли ЭТОТ пользователь ЭТОТ промокод ранее
    cursor.execute('SELECT 1 FROM promocode_activations WHERE code = ? AND user_id = ?', (code, user_id))
    already_activated_by_me = cursor.fetchone()
    if already_activated_by_me:
        conn.close()
        return "YOU_ALREADY_USED" # Личная ошибка: вы этот код уже вводили

    # 3. Проверяем глобальный лимит использований (только если max_uses > 0, то есть код не бесконечный)
    if max_uses > 0 and current_uses >= max_uses:
        conn.close()
        return "ALREADY_USED" # Код исчерпал лимиты полностью

    # 4. Если всё отлично, фиксируем активацию
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        # Логируем, что этот юзер ввел этот код
        cursor.execute(
            'INSERT INTO promocode_activations (code, user_id, activated_at) VALUES (?, ?, ?)',
            (code, user_id, now_str)
        )
        # Увеличиваем счетчик использований промокода на +1
        cursor.execute(
            'UPDATE promocodes SET current_uses = current_uses + 1 WHERE code = ?',
            (code,)
        )
        conn.commit()
        return days
    except sqlite3.IntegrityError:
        conn.close()
        return "YOU_ALREADY_USED"
    finally:
        conn.close()


def delete_promocode_from_db(code: str) -> bool:
    """Полностью удаляет промокод из базы данных. Возвращает True, если код существовал и удален."""
    code = code.strip().upper()
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    # Сначала проверяем, есть ли такой код
    cursor.execute('SELECT 1 FROM promocodes WHERE code = ?', (code,))
    exists = cursor.fetchone()
    
    if not exists:
        conn.close()
        return False
        
    # Удаляем промокод
    cursor.execute('DELETE FROM promocodes WHERE code = ?', (code,))
    conn.commit()
    conn.close()
    return True





def add_referral_connection(inviter_id: int, referral_id: int):
    """Фиксирует приглашение в базе данных"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO referral_connections (inviter_id, referral_id) VALUES (?, ?)',
            (inviter_id, referral_id)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Защита от дублей, если связь уже записана
    finally:
        conn.close()

def get_monthly_top_inviters(limit: int = 10):
    """Возвращает ТОП пользователей по приглашениям за последние 30 дней"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    
    # Считаем приглашения за последние 30 дней, склеиваем с таблицей users для получения красивого username
    cursor.execute('''
        SELECT 
            r.inviter_id, 
            u.username, 
            COUNT(r.referral_id) as invite_count
        FROM referral_connections r
        LEFT JOIN users u ON r.inviter_id = u.user_id
        WHERE r.created_at >= datetime('now', '-30 days', 'localtime')
        GROUP BY r.inviter_id
        ORDER BY invite_count DESC
        LIMIT ?
    ''', (limit,))
    
    top_list = cursor.fetchall()
    conn.close()
    return top_list # Возвращает список кортежей: [(inviter_id, username, count), ...]



def get_user_invite_count(user_id: int) -> int:
    """Возвращает общее количество приглашенных пользователем людей за все время"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM referral_connections WHERE inviter_id = ?', (user_id,))
    count = cursor.fetchone()[0] 
    conn.close()
    return count


def save_user_device_prefs(user_id, os_name, app_name):
    """Быстрое сохранение только ОС и приложения без изменения остальных полей"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET saved_os = ?, saved_app = ? WHERE user_id = ?', (os_name, app_name, user_id))
    conn.commit()
    conn.close()

def clear_user_device_prefs(user_id):
    """Сброс настроек устройства (запись NULL в базу)"""
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET saved_os = NULL, saved_app = NULL WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()







SERVERS = [
    {
        "id": "fi_1",
        "panel_url": "http://78.17.11.14:2053",
        "base_path": "/xD2SJTfdphAmQqisoB", 
        "panel_user": "Asad",
        "panel_password": "Lodka120259",
        "inbound_id": 1,
        "my_ip": "78.17.11.14",
        "pbk": "GMs90LvYkQoeBfFcvbFxvSOqV9BCGleUliZueyNrZQ0", 
        "sid": "d35e733e16c7a4d0", 
        "sni": "www.amd.com",                           
        "country_flag": "🇫🇮",
        "country_name": "Финляндия"
    },
    {
        "id": "de_1",
        "panel_url": "https://sonatavpn.ru", 
        "base_path": "/dsjwEGmmrbon",
        "panel_user": "Soul",
        "panel_password": "Lodka1321",
        "inbound_id": 1,
        "my_ip": "78.17.152.36",
        "pbk": "wEXAYpBWeoSjHYgUc75Jpze2cyAkefqNDXn6JTKPNlQ", 
        "sid": "bfb0e0d2c85acc", 
        "sni": "www.sony.com",                                   
        "country_flag": "🇵🇱",
        "country_name": "Польша"
    },
    {
        "id": "ru_bridge_1",
        "panel_url": "https://217.171.146.33:2053",
        "base_path": "/0wlhvqnD4d2O1ggT8d", # Добавили слэш в начало пути, чтобы .ru/ работал идеально  
        "panel_user": "Asad",  
        "panel_password": "542013",  
        "inbound_id": 1,  
        "my_ip": "158.160.233.149",  # ПРЯМО СЮДА СТАВИМ БЕЛЫЙ IP ЯНДЕКСА!
        "pbk": "16N7o9hxq1tVpLqsR242g9zonP9EJ4qTiHHNvSZbjUk",  
        "sid": "29a872b6",  
        "sni": "yandex.ru",  
        "country_flag": "🇷🇺",
        "country_name": "Обход №1"
    }
]


async def get_vpn_config_clean(user_id, username=""):
    vless_links = []
    final_expiry_time_ms = 0
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
        for srv in SERVERS:
            try:
                email_for_panel = f"{srv['country_flag']}_{srv['country_name']}_#{user_id}".replace(" ", "_")
                
                # 1. Авторизация (Классический рабочий метод)
                login_url = f"{srv['panel_url']}{srv['base_path']}/login"
                async with session.post(login_url, data={"username": srv['panel_user'], "password": srv['panel_password']}, timeout=10) as resp:
                    await resp.text()

                headers = {"Accept": "application/json"}

                # 2. Получение данных инбаунда
                get_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/get/{srv['inbound_id']}"
                async with session.get(get_url, headers=headers, timeout=10) as resp:
                    res_json = await resp.json()
                    
                if not res_json.get("success"):
                    logging.error(f"Панель {srv['id']} вернула ошибку при GET: {res_json}")
                    continue

                settings = json.loads(res_json["obj"]["settings"])
                clients = settings.get("clients", [])
                
                current_client = next((c for c in clients if c.get("tgId") == user_id), None)
                if not current_client:
                    old_email = f"user_{user_id}"
                    current_client = next((c for c in clients if c.get("email") == old_email), None)

                client_uuid = current_client.get("id") if current_client else None

                # 3. Добавление или обновление клиента
                if not client_uuid:
                    client_uuid = str(uuid.uuid4())
                    sub_id = secrets.token_hex(8)
                    
                    add_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/addClient"
                    client_data = {
                        "id": str(srv['inbound_id']), 
                        "settings": json.dumps({"clients": [{
                            "id": client_uuid, "email": email_for_panel, "limitIp": 2, "totalGB": 0,
                            "expiryTime": 0, "enable": True, "tgId": user_id, "subId": sub_id  
                        }]})
                    }
                    async with session.post(add_url, headers=headers, data=client_data, timeout=10) as r:
                        await r.text()
                    expiry_time_ms = 0
                else:
                    expiry_time_ms = current_client.get("expiryTime", 0)
                    sub_id = current_client.get("subId", "")
                    if not sub_id:
                        sub_id = secrets.token_hex(8)
                        
                    update_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/updateClient/{client_uuid}"
                    client_data = {
                        "id": str(srv['inbound_id']),
                        "settings": json.dumps({"clients": [{
                            "id": client_uuid, "email": email_for_panel, "limitIp": current_client.get("limitIp", 2),
                            "totalGB": current_client.get("totalGB", 0), "expiryTime": expiry_time_ms, "enable": current_client.get("enable", True), "tgId": user_id, "subId": sub_id  
                        }]})
                    }
                    async with session.post(update_url, headers=headers, data=client_data, timeout=10) as r:
                        await r.text()

                if expiry_time_ms > 0:
                    final_expiry_time_ms = expiry_time_ms

                # Хак для порта нового моста Яндекса
                if srv["id"] == "ru_bridge_1":
                    my_port = 443
                else:
                    my_port = res_json["obj"]["port"]
                
                # 4. Сборка ссылки строго по вашему рабочему эталону           
                if srv["id"] == "fi_1":
                    remark = f"{srv['country_flag']} {srv['country_name']}"
                    safe_remark = remark  # ИСПРАВЛЕНО: убрали quote
                    current_fp = "firefox"
                elif srv["id"] == "ru_bridge_1":
                    remark = f"{srv['country_flag']} {srv['country_name']}"
                    safe_remark = remark  # ИСПРАВЛЕНО: убрали quote
                    current_fp = "firefox"
                else:
                    remark = f"{srv['country_flag']}{srv['country_name']}"
                    safe_remark = remark  # ИСПРАВЛЕНО: убрали quote
                    current_fp = "chrome"
                
                # Полное посимвольное соответствие вашей структуре, но без лишнего слэша перед ремаркой
                config_link = (
                    f"vless://{client_uuid}@{srv['my_ip']}:{my_port}"
                    f"?flow=&type=tcp&headerType=none&security=reality&fp={current_fp}"
                    f"&sni={srv['sni']}&pbk={srv['pbk']}&sid={srv['sid']}#{safe_remark}"
                )
                    
                vless_links.append(config_link)


            except Exception as e:
                logging.error(f"Ошибка сервера {srv['id']}: {e}", exc_info=True)
                continue

    return vless_links, final_expiry_time_ms




#-------------нагрузки на сервера, функция---------


async def fetch_real_server_load(srv):
    """
    Делает запрос к API 3X-UI и возвращает реальный процент загрузки CPU.
    Автоматически перебирает пути, если сервер выдает 404.
    """
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
        try:
            # 1. Авторизация на сервере (строго POST)
            login_url = f"{srv['panel_url']}{srv['base_path']}/login"
            async with session.post(login_url, data={"username": srv['panel_user'], "password": srv['panel_password']}, timeout=5) as resp:
                await resp.text()
                
            headers = {"Accept": "application/json"}
            
            # Список эндпоинтов для проверки (сначала новый API-путь, затем старый прямой)
            endpoints = [
                f"{srv['panel_url']}{srv['base_path']}/panel/api/server/status",
                f"{srv['panel_url']}{srv['base_path']}/server/status"
            ]
            
            res_json = None
            
            # Перебираем пути, пока не найдем рабочий
            for status_url in endpoints:
                async with session.get(status_url, headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        try:
                            res_json = await resp.json()
                            if res_json.get("success") and "obj" in res_json:
                                # Если данные успешно получены, прерываем цикл перебора путей
                                break
                        except Exception:
                            # Если не удалось распарсить JSON, идем к следующему эндпоинту
                            continue
                    elif resp.status == 404:
                        # Если 404, просто пробуем следующий путь в цикле
                        continue
            
            # Если ни один путь не вернул успех
            if not res_json or not res_json.get("success") or "obj" not in res_json:
                logging.error(f"❌ Сервер {srv['id']} не отдал статус ни по одному из известных эндпоинтов.")
                return None
                
            # Извлекаем чистый процент загрузки процессора
            cpu_load = res_json["obj"].get("cpu", 0)
            return int(cpu_load)
                
        except Exception as e:
            logging.error(f"❌ Критическая ошибка получения статуса для сервера {srv['id']}: {e}")
            return None






async def send_sub_to_website(token, b64_content, expiry, is_blocked=False):
    """
    Отправляет рабочий Base64 или пустую строку при блокировке на PHP-сайт.
    Добавлен аргумент is_blocked для принудительного затирания серверов.
    """
    url = "https://sonatavpn.ru" + "/" + "index.php?update_sub=1"
    import time

    try:
        expiry_int = int(expiry)
    except (ValueError, TypeError):
        expiry_int = 1893456000

    # ЖЕЛЕЗНАЯ ПРОВЕРКА: Если передан флаг блокировки ИЛИ время реально вышло
    if is_blocked or expiry_int <= int(time.time()):
        content_to_send = ""
        logging.info(f"[МАРШРУТИЗАЦИЯ] Пользователь {token} заблокирован/истек. Отправляем пустоту.")
    else:
        content_to_send = b64_content

    data = {
        "token": token,
        "content": content_to_send,
        "expiry": expiry_int
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=5) as response:
                res_text = await response.text()
                logging.info(f"[МАРШРУТИЗАЦИЯ] Синхронизация токена {token}: {res_text}")
    except Exception as ex:
        logging.error(f"[ОШИБКА] Не удалось передать подписку: {ex}")

    
















# ==================== СТРОГИЕ ФИЛЬТРЫ БЕЗОПАСНОСТИ ====================

from aiogram.filters import BaseFilter
from aiogram import types

class IsCreator(BaseFilter):
    """Фильтр строго для Создателя (Владельца ADMIN_ID)"""
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id == ADMIN_ID

class IsAdmin(BaseFilter):
    """Фильтр для Администраторов (Управление подписками)"""
    async def __call__(self, message: types.Message) -> bool:
        if message.from_user.id == ADMIN_ID:
            return True
        user = get_user_from_db(message.from_user.id)
        # ИСПРАВЛЕНО: Проверяем длину кортежа и смотрим строго на индекс 5 (поле role)
        return user is not None and len(user) > 5 and user[5] == 'admin'

class IsAmbassador(BaseFilter):
    """Фильтр для Амбассадоров (Управление промокодами)"""
    async def __call__(self, message: types.Message) -> bool:
        if message.from_user.id == ADMIN_ID:
            return True
        user = get_user_from_db(message.from_user.id)
        # ИСПРАВЛЕНО: Проверяем длину кортежа и смотрим строго на индекс 5 (поле role)
        return user is not None and len(user) > 5 and user[5] == 'ambassador'






#-----------команды------------



@dp.message(F.text.startswith("/team"), IsCreator())
async def handle_show_team(message: types.Message):
    """Выводит полный список Администраторов и Амбассадоров с их статистикой действий"""
    
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    # Выгружаем персонал (ID, имя, роль, и наши новые счетчики действий)
    cursor.execute("SELECT user_id, username, role, actions_gift, actions_gen FROM users WHERE role IN ('admin', 'ambassador')")
    team_members = cursor.fetchall()
    conn.close()

    if not team_members:
        await message.answer(
            "👥 <b>Команда Sonata VPN</b>\n\n"
            "<blockquote>❌ В вашей команде пока нет ни одного администратора или амбассадора.</blockquote>\n"
            "Вы можете назначить их с помощью команды:\n<code>/setrole [ID] [admin/ambassador]</code>",
            parse_mode="HTML"
        )
        return

    # Разделяем сотрудников по спискам
    admins_list = []
    ambassadors_list = []

    for member in team_members:
        tg_id = member[0]
        username = f"@{member[1]}" if member[1] and member[1] != "Unknown" else "<i>Нет юзернейма</i>"
        role = member[2]
        gifts_count = member[3] if member[3] is not None else 0
        gens_count = member[4] if member[4] is not None else 0

        if role == "admin":
            admins_list.append(f"• 👤 ID: <code>{tg_id}</code> | {username}\n  └ 📊 Выдано подписок (/gift): <b>{gifts_count} шт.</b>")
        elif role == "ambassador":
            ambassadors_list.append(f"• 👤 ID: <code>{tg_id}</code> | {username}\n  └ 📊 Создано промокодов (/gen): <b>{gens_count} шт.</b>")

    # Сборка финального сообщения
    report_text = "👑 <b>Управление командой Sonata VPN</b>\n\n"

    # Секция Администраторов (Красная плашка)
    report_text += "🔴 <b>АДМИНИСТРАТОРЫ (Управление подписками):</b>\n"
    if admins_list:
        # Упаковываем весь список админов в один фиолетовый блок цитаты
        report_text += "<blockquote>" + "\n\n".join(admins_list) + "</blockquote>\n\n"
    else:
        report_text += "<blockquote><i>Администраторы не назначены</i></blockquote>\n\n"

    # Секция Амбассадоров (Оранжевая плашка)
    report_text += "🟠 <b>АМБАССАДОРЫ (Управление промокодами):</b>\n"
    if ambassadors_list:
        # Упаковываем весь список амбассадоров в один фиолетовый блок цитаты
        report_text += "<blockquote>" + "\n\n".join(ambassadors_list) + "</blockquote>\n\n"
    else:
        report_text += "<blockquote><i>Амбассадоры не назначены</i></blockquote>\n\n"

    report_text += (
        "💡 <i>Чтобы снять права и аннулировать безлимитный VPN сотрудника, используйте команду:</i>\n"
        "<code>/demote [ID]</code>"
    )

    await message.answer(report_text, parse_mode="HTML")






from aiogram import types, F
from aiogram.filters import Command

# Вспомогательный словарь для красивого вывода ролей
ROLE_NAMES = {
    "admin": "🛡️ Администратор | Staff",
    "ambassador": "✨ Амбассадор | Partner",
    "user": "👤 Обычный пользователь"
}

@dp.message(F.text.startswith("/panel"), IsCreator())
async def creator_panel_help(message: types.Message):
    """Справка по управлению ролями для Создателя"""
    await message.answer(
        "👑 <b>Панель управления ролями (Доступно только Создателю)</b>\n\n"
        "Вы можете выдавать и забирать права у пользователей по их Telegram ID:\n\n"
        "• <b>Назначить роль:</b>\n"
        "<code>/setrole [ID] admin</code> — назначить администратора\n"
        "<code>/setrole [ID] ambassador</code> — назначить амбассадора\n\n"
        "• <b>Разжаловать до юзера:</b>\n"
        "<code>/demote [ID]</code> — вернуть статус обычного пользователя\n\n"
        "Рассылка: <code>/send</code>\n"
        "• Одноразовый: <code>/gen [дни] [код]</code>\n"
        "• Бесконечный: <code>/gen [дни] [код] 0</code>\n"
        "• Лимитированный: <code>/gen [дни] [код] [кол-во_человек]</code>" 
        "<i>💡 ID пользователя можно узнать в его Личном кабинете или скопировать из логов.</i>",
        parse_mode="HTML"
    )


@dp.message(F.text.startswith("/setrole"), IsCreator())
async def handle_set_role(message: types.Message):
    parts = message.text.split()
    
    if len(parts) < 3:
        await message.answer(
            "⚠️ <b>Неверный формат команды!</b>\n"
            "Используйте: <code>/setrole [ID_пользователя] [admin/ambassador]</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_user_id = int(parts[1])
        requested_role = parts[2].strip().lower()

        if requested_role not in ["admin", "ambassador"]:
            await message.answer("❌ <b>Ошибка:</b> Допустимые роли только: <code>admin</code> или <code>ambassador</code>")
            return

        # Проверяем наличие юзера в вашей локальной БД
        user_in_db = get_user_from_db(target_user_id)
        if not user_in_db:
            await message.answer(
                f"❌ <b>Пользователь с ID <code>{target_user_id}</code> не найден в базе данных!</b>\n"
                f"Он должен хотя бы раз запустить бота через /start."
            )
            return

        # 1. Записываем новую роль в SQLite3
        set_user_role(target_user_id, requested_role)
        
        # Уведомляем админа о начале синхронизации
        await message.answer(f"⏳ Роль изменена. Синхронизирую безлимитную подписку на серверах X-UI для {target_user_id}...")

        # 2. Вызываем функцию безлимита на серверах и локально (наша прошлая функция)
        await grant_infinity_access_for_staff(target_user_id)

        # Выводим красивый ответ в зависимости от выданной роли
        if requested_role == "admin":
            role_report = "<blockquote>🔴 НАЗНАЧЕН: АДМИНИСТРАТОР\n⚙️ Статус: Доступ к /gift и /revoke открыт\n♾️ Подписка: Активирован безлимит</blockquote>"
            user_notify = "🔴 <b>Внимание!</b> Создатель назначил вас Администратором. Вам доступно управление подписками через /gift и /revoke, а также выдан безлимитный VPN!"
        else:
            role_report = "<blockquote>🟠 НАЗНАЧЕН: АМБАССАДОР\n⚙️ Статус: Доступ к /gen и /delpromo открыт\n♾️ Подписка: Активирован безлимит</blockquote>"
            user_notify = "🟠 <b>Внимание!</b> Создатель назначил вас Амбассадором. Вам доступно управление промокодами через /gen и /delpromo, а также выдан безлимитный VPN!"

        await message.answer(
            f"👑 <b>Права пользователя успешно обновлены!</b>\n\n"
            f"{role_report}",
            parse_mode="HTML"
        )
        
        # Отправляем уведомление самому пользователю
        try:
            await message.bot.send_message(chat_id=target_user_id, text=user_notify, parse_mode="HTML")
        except Exception:
            pass

    except ValueError:
        await message.answer("❌ <b>Ошибка:</b> Telegram ID должен состоять только из цифр!")




@dp.message(F.text.startswith("/demote"), IsCreator())
async def handle_demote_user(message: types.Message):
    """Полное снятие прав и возвращение к роли обычного юзера"""
    parts = message.text.split()
    
    if len(parts) < 2:
        await message.answer(
            "⚠️ <b>Неверный формат команды!</b>\n"
            "Используйте: <code>/demote [ID_пользователя]</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_user_id = int(parts[1])

        user_in_db = get_user_from_db(target_user_id)
        if not user_in_db:
            await message.answer(f"❌ Пользователь с ID <code>{target_user_id}</code> не найден в БД.")
            return

        # Возвращаем дефолтную роль 'user'
        set_user_role(target_user_id, "user")
        
        await message.answer(f"⏳ Разжалую пользователя {target_user_id}. Отзываю безлимитную подписку со всех серверах X-UI...")

        # 2. Вызываем вашу родную функцию аннулирования подписки (она отключит в панели и сбросит expiry_time в 0)
        is_revoked = await revoke_vpn_subscription(target_user_id)

        if is_revoked:
            status_vpn = "🟢 Успешно отключен везде и обнулен"
        else:
            status_vpn = "⚠️ Роль снята, но в панелях X-UI пользователь не найден (возможно, удален ранее)"

        # Вывод красивого фиолетового отчета для вас
        await message.answer(
            f"🔨 <b>Пользователь разжалован!</b>\n\n"
            f"<blockquote>👤 Пользователь: {target_user_id}\n"
            f"🏷️ Текущая роль: Обычный пользователь\n"
            f"🔴 Доступ: Административные привилегии отозваны</blockquote>",
            parse_mode="HTML"
        )

        try:
            await message.bot.send_message(
                chat_id=target_user_id,
                text="⚠️ Ваш административный статус в боте был аннулирован Создателем. Вы переведены в режим обычного пользователя."
            )
        except Exception:
            pass

    except ValueError:
        await message.answer("❌ <b>Ошибка:</b> Telegram ID должен состоять только из цифр!")


#-----с пользователями и создание---



import asyncio
from aiogram import types
from aiogram.filters import Command

@dp.message(Command("top"))
async def cmd_top_inviters(message: types.Message):
    # Отправляем предварительное сообщение, так как запросы имен из TG API могут занять пару секунд
    loading_msg = await message.answer("📊 <b>Загрузка рейтинга лидеров...</b>", parse_mode="HTML")
    
    # Получаем данные из БД за последние 30 дней
    top_data = get_monthly_top_inviters(limit=10)
    
    if not top_data:
        await loading_msg.edit_text("📊 Топ приглашающих за месяц:\n\nПока никто никого не пригласил. Будьте первыми!")
        return

    text = "🏆 <b>ТОП-10 лидеров по приглашениям за 30 дней</b>\n\n"
    
    # Иконки для первых трех мест
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    
    for index, row in enumerate(top_data, start=1):
        inviter_id, username, count = row
        
        # --- ПОЛУЧЕНИЕ НАСТОЯЩЕГО ИМЕНИ ИЗ TELEGRAM ---
        try:
            # Запрашиваем информацию о чате пользователя напрямую у Telegram
            chat_info = await message.bot.get_chat(inviter_id)
            # Берем имя (First Name). Если у человека есть фамилия, можно сделать f"{chat_info.first_name} {chat_info.last_name or ''}"
            display_name = chat_info.first_name
        except Exception:
            # Если бот не смог достучаться до API (юзер удален/заблокировал бота), используем старый username или заглушку
            display_name = f"@{username}" if username and username != "Unknown" else "Пользователь"

        # Создаем красивое текстовое упоминание (работает для всех, даже если нет @username)
        # При клике на имя откроется профиль человека
        user_mention = f'<a href="tg://user?id={inviter_id}">{display_name}</a>'
        
        # Определяем эмодзи места (медаль или просто цифра)
        place_emoji = medals.get(index, f"<code>{index}.</code>")
        
        # Склоняем слово "человек" в зависимости от количества
        if count % 10 == 1 and count % 100 != 11:
            word = "человек"
        else:
            word = "человек(а)"
            
        text += f"{place_emoji} {user_mention} — <b>{count}</b> {word}\n"
        # Небольшая микропауза, чтобы Telegram API не выдал ошибку Flood Wait при частых запросах get_chat
        await asyncio.sleep(0.1)
        
    text += "\n\n<i>Зовите друзей по своей реферальной ссылке и поднимайтесь в рейтинге!</i>"
    
    # Редактируем сообщение о загрузке на финальный красивый топ
    try:
        await loading_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    except Exception:
        # Если вдруг редактирование не сработало, просто отправляем новым сообщением
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)






@dp.message(Command("gen"), IsAmbassador())
async def handle_generate_promo(message: types.Message):
     

    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "Использование:\n"
            "• Одноразовый: <code>/gen [дни] [код]</code>\n"
            "• Бесконечный: <code>/gen [дни] [код] 0</code>\n"
            "• Лимитированный: <code>/gen [дни] [код] [кол-во_человек]</code>", 
            parse_mode="HTML"
        )
        return
        
    try:
        days = int(parts[1])
        custom_code = parts[2].strip().upper() if len(parts) > 2 else None
        
        # Определяем лимит использований (если указан 3-й параметр, берем его, иначе ставим 1)
        max_uses = int(parts[3]) if len(parts) > 3 else 1
        
        # Вызываем обновленную генерацию
        result_code = generate_new_promocode(days, custom_code, max_uses)
        conn = sqlite3.connect(DB_PATH); conn.cursor().execute("UPDATE users SET actions_gen = actions_gen + 1 WHERE user_id = ?", (message.from_user.id,)); conn.commit(); conn.close()
        
        if result_code == "EXISTS":
            await message.answer("❌ Такой кастомный промокод уже существует в базе данных!")
            return
            
        # Формируем красивый статус для админа
        if max_uses == 0:
            uses_text = "♾ Без ограничений (каждый юзер по 1 разу)"
        elif max_uses == 1:
            uses_text = "👤 Одноразовый (для 1 человека)"
        else:
            uses_text = f"👥 Ограниченный (для {max_uses} разных человек)"

        await message.answer(
            f"🎟 <b>Промокод успешно создан!</b>\n\n"
            f"🔑 Код: <code>{result_code}</code>\n"
            f"⏳ Срок: <b>{days} дней</b>\n"
            f"📊 Лимит активаций: <b>{uses_text}</b>\n\n"
            f"<i>Вы можете передать его пользователям.</i>", 
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Ошибка: количество дней и лимит активаций должны быть целыми числами.")





@dp.message(F.text.startswith("/promo") | F.text.startswith("/activate"))
async def handle_promo_activation(message: types.Message): # Используем types.Message
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "⚠️ <b>Пожалуйста, укажите промокод!</b>\n\n"
            "Пример ввода:\n<code>/promo СONATA_FREE</code> (нажмите для копирования)", 
            parse_mode="HTML"
        )
        return
        
    promo_code = parts[1].strip().upper()
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    # 1. Проверяем и гасим промокод в локальной SQLite
    db_result = activate_promo_in_db(promo_code, user_id)
    
    if db_result == "NOT_FOUND":
        await message.answer("❌ <b>Такого промокода не существует.</b> Проверьте правильность букв.", parse_mode="HTML")
        return
    elif db_result == "ALREADY_USED":
        await message.answer("❌ <b>Этот промокод больше не активен.</b> Лимит его активаций полностью исчерпан.", parse_mode="HTML")
        return
    elif db_result == "YOU_ALREADY_USED":
        await message.answer("❌ <b>Вы уже активировали этот промокод ранее!</b> Повторная активация невозможна.", parse_mode="HTML")
        return
        
    # Если проверка успешна, db_result вернет количество дней (int)
    days_to_add = db_result
    status_msg = await message.answer(f"🔄 Промокод принят!\n Начисляю {days_to_add} дней подписки и обновляю сервера...")
    
    try:
        # 2. Запуск комплексного обновления (Панели + Локальная БД + Сайт)
        await apply_subscription_extension(user_id, username, days_to_add)
        
        # Получаем обновленную дату для красивого вывода пользователю
        user_data = get_user_from_db(user_id)
        
        # ИСПРАВЛЕНО: Используем правильный индекс [4] и приводим к числу int
        try:
            updated_expiry = int(user_data[4]) if (user_data and len(user_data) > 4 and user_data[4] is not None) else 0
        except (ValueError, TypeError):
            updated_expiry = 0
            
        expiry_date = datetime.fromtimestamp(updated_expiry).strftime('%d.%m.%Y в %H:%M')


        
        await status_msg.edit_text(
            f"✅ <b>Промокод успешно активирован!</b>\n\n"
            f"➕ Начислено: <b>{days_to_add} дней</b>\n"
            f"📅 Новая дата окончания: <b>{expiry_date}</b>\n\n"
            f"<i>💡 Конфигурации на вашем устройстве обновятся автоматически, переподключать заново ничего не нужно!</i>",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка выполнения apply_subscription_extension для {user_id}: {e}", exc_info=True)
        await status_msg.edit_text(
            "⚠️ <b>Промокод зафиксирован, но произошел сбой обновления серверов.</b>\n"
            "Пожалуйста, напишите администратору, вам начислят дни вручную.", 
            parse_mode="HTML"
        )




@dp.message(Command("delpromo"), IsAmbassador())
async def handle_delete_promo(message: types.Message):
    
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer(
            "⚠️ <b>Пожалуйста, укажите промокод для удаления!</b>\n\n"
            "Пример использования:\n<code>/delpromo SONATA-A1B2C3D4</code>", 
            parse_mode="HTML"
        )
        return
        
    promo_code = parts[1].strip().upper()
    
    # Вызываем функцию удаления из БД
    is_deleted = delete_promocode_from_db(promo_code)
    
    if is_deleted:
        await message.answer(
            f"🗑 <b>Промокод успешно удален!</b>\n\n"
            f"🔑 Код: <code>{promo_code}</code>\n"
            f"❌ Больше никто не сможет его активировать.", 
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"❌ <b>Ошибка:</b> Промокод <code>{promo_code}</code> не найден в базе данных.", 
            parse_mode="HTML"
        )











async def grant_infinity_access_for_staff(user_id: int) -> bool:
    """
    Автоматически выдает безлимитную подписку (до 2099 года) 
    для Администраторов, Амбассадоров и Создателя на всех серверах 3X-UI и в локальной БД.
    """
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    infinity_expiry_ms = 4070908800 * 1000 
    infinity_expiry_seconds = 4070908800

    any_server_updated = False

    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            for srv in SERVERS:
                try:
                    email_for_panel = f"{srv['country_flag']}_{srv['country_name']}_#{user_id}".replace(" ", "_")
                    
                    login_url = f"{srv['panel_url']}{srv['base_path']}/login"
                    async with session.post(login_url, data={"username": srv['panel_user'], "password": srv['panel_password']}, timeout=10) as resp:
                        await resp.text()

                    headers = {"Accept": "application/json"}

                    get_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/get/{srv['inbound_id']}"
                    async with session.get(get_url, headers=headers, timeout=10) as resp:
                        res_json = await resp.json()

                    if not res_json.get("success"):
                        continue

                    settings = json.loads(res_json["obj"]["settings"])
                    clients = settings.get("clients", [])

                    current_client = next((c for c in clients if c.get("tgId") == user_id), None)
                    if not current_client:
                        old_email = f"user_{user_id}"
                        current_client = next((c for c in clients if c.get("email") == old_email), None)

                    if not current_client:
                        continue

                    client_uuid = current_client['id']
                    update_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/updateClient/{client_uuid}"
                    
                    client_data = {
                        "id": str(srv['inbound_id']),
                        "settings": json.dumps({
                            "clients": [{
                                "id": client_uuid,
                                "email": email_for_panel,
                                "limitIp": current_client.get("limitIp", 5),
                                "totalGB": 0,
                                "expiryTime": infinity_expiry_ms,
                                "enable": True,
                                "tgId": user_id,
                                "subId": current_client.get("subId", "")
                            }]
                        })
                    }

                    async with session.post(update_url, headers=headers, data=client_data, timeout=10) as resp:
                        update_resp = await resp.json()

                    if update_resp.get("success", False):
                        any_server_updated = True

                except Exception as srv_err:
                    logging.error(f"Ошибка безлимита на сервере {srv['id']}: {srv_err}")
                    continue

        if any_server_updated:
            user_data = get_user_from_db(user_id)
            # ИСПРАВЛЕНО: Извлекаем username из кортежа по индексу 1
            current_username = user_data[1] if (user_data and len(user_data) > 1) else ""
            
            # Записываем в БД вечный timestamp
            add_or_update_user(user_id, current_username, expiry_time=infinity_expiry_seconds)
            return True
            
        return False

    except Exception as e:
        logging.error(f"Ошибка в grant_infinity_access_for_staff: {e}")
        return False









async def apply_subscription_extension(user_id: int, username: str, days_to_add: int):
    """
    Полностью продлевает подписку пользователя:
    1. Пересчитывает время (в БД секунды, на панелях мс)
    2. Обновляет 3X-UI панели
    3. Перезапускает генерацию конфигов и пушит новый Base64 на сайт
    """
    # ---- 1. Расчет времени ----
    user_data = get_user_from_db(user_id)
    
    # ИСПРАВЛЕНО: берем индекс [4] (expiry_time) вместо [3] и принудительно переводим в int
    try:
        current_expiry_seconds = int(user_data[4]) if (user_data and len(user_data) > 4 and user_data[4] is not None) else 0
    except (ValueError, TypeError):
        current_expiry_seconds = 0
    
    current_time_seconds = int(time.time())
    seconds_to_add = days_to_add * 24 * 60 * 60
    
    # Если подписка истекла или равна 0 -> считаем от сейчас
    if current_expiry_seconds <= current_time_seconds:
        new_expiry_seconds = current_time_seconds + seconds_to_add
    else:
        # Если еще активна -> плюсуем сверху
        new_expiry_seconds = current_expiry_seconds + seconds_to_add
        
    new_expiry_ms = new_expiry_seconds * 1000 # Для панелей переводим в мс


    # ---- 2. Обновление внешних панелей 3X-UI ----
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
        for srv in SERVERS:
            try:
                email_for_panel = f"{srv['country_flag']}_{srv['country_name']}_#{user_id}".replace(" ", "_")
                
                # Авторизация на панели
                login_url = f"{srv['panel_url']}{srv['base_path']}/login"
                async with session.post(login_url, data={"username": srv['panel_user'], "password": srv['panel_password']}, timeout=10) as resp:
                    await resp.text()

                headers = {"Accept": "application/json"}

                # Получение данных инбаунда
                get_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/get/{srv['inbound_id']}"
                async with session.get(get_url, headers=headers, timeout=10) as resp:
                    res_json = await resp.json()
                    
                if not res_json.get("success"):
                    continue

                settings = json.loads(res_json["obj"]["settings"])
                clients = settings.get("clients", [])
                
                current_client = next((c for c in clients if c.get("tgId") == user_id), None)
                if not current_client:
                    old_email = f"user_{user_id}"
                    current_client = next((c for c in clients if c.get("email") == old_email), None)

                # Если клиента нет, создаем базового через ваш чистый метод
                if not current_client:
                    await get_vpn_config_clean(user_id, username)
                    async with session.get(get_url, headers=headers, timeout=10) as r_retry:
                        res_json = await r_retry.json()
                    settings = json.loads(res_json["obj"]["settings"])
                    current_client = next((c for c in settings.get("clients", []) if c.get("tgId") == user_id), None)

                if not current_client:
                    continue

                client_uuid = current_client.get("id")
                sub_id = current_client.get("subId", secrets.token_hex(8))

                # Отправляем новый expiryTime (в мс) на панель
                update_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/updateClient/{client_uuid}"
                client_data = {
                    "id": str(srv['inbound_id']),
                    "settings": json.dumps({"clients": [{
                        "id": client_uuid,
                        "email": email_for_panel,
                        "limitIp": current_client.get("limitIp", 2),
                        "totalGB": current_client.get("totalGB", 0),
                        "expiryTime": new_expiry_ms, 
                        "enable": True,
                        "tgId": user_id,
                        "subId": sub_id  
                    }]})
                }
                async with session.post(update_url, headers=headers, data=client_data, timeout=10) as r:
                    await r.text()

            except Exception as e:
                logging.error(f"Ошибка применения промокода на сервере {srv['id']}: {e}")

    # ---- 3. Генерация обновленного Base64 и синхронизация с сайтом ----
    try:
        vless_links, _ = await get_vpn_config_clean(user_id, username)
        combined_configs = "\n".join(vless_links) if vless_links else ""
        base64_payload = base64.b64encode(combined_configs.strip().encode('utf-8')).decode('utf-8')
        
        sub_id = "e" + hashlib.md5(str(user_id).encode()).hexdigest()[:15]
        
        await send_sub_to_website(sub_id, base64_payload, new_expiry_seconds)
        add_or_update_user(user_id, username, combined_configs, sub_id, new_expiry_seconds)
        
    except Exception as e:
        logging.error(f"Ошибка синхронизации сайта при промокоде: {e}")
        add_or_update_user(user_id, username, None, None, new_expiry_seconds)






async def renew_vpn_subscription(user_id: int) -> bool:
    """
    Стандартная функция продления подписки на 30 дней для платежной системы ЮKassa.
    Итерируется по всем серверам из SERVERS, рассчитывает время, 
    активирует клиентов и обновляет локальную БД Amvera вместе с сайтом.
    """
    try:
        logging.info(f"💳 [ЮKassa] Получено уведомление об оплате. Запуск продления на 30 дней для ID: {user_id}")
        
        # Получаем имя пользователя из БД, чтобы не затереть его при обновлении
        user_data = get_user_from_db(user_id)
        username = user_data[0] if (user_data and len(user_data) > 0) else ""
        
        # Вызываем нашу универсальную функцию гибкого продления на 30 дней
        success = await renew_vpn_subscription_flexible(user_id=user_id, days=30, username=username)
        
        if success:
            logging.info(f"✅ [ЮKassa] Подписка для пользователя {user_id} успешно продлена на 30 дней на всех серверах.")
            return True
        else:
            logging.error(f"❌ [ЮKassa] Ошибка при вызове гибкого продления для пользователя {user_id}.")
            return False
            
    except Exception as e:
        logging.error(f"⚠️ Критическая ошибка внутри renew_vpn_subscription (ЮKassa) для {user_id}: {e}", exc_info=True)
        return False


async def renew_vpn_subscription_flexible(user_id: int, days: int, username: str = ""):
    """
    Продлевает подписку на указанное количество дней на ВСЕХ серверах из SERVERS.
    Если подписка активна — прибавляет дни сверху. Если истекла — считает от текущего момента.
    Активирует/включает клиентов в X-UI панелях и сохраняет в локальную БД.
    """
    # ---- 1. Расчет времени (Секунды для БД, Миллисекунды для панелей) ----
    user_data = get_user_from_db(user_id)
    # Извлекаем именно ячейку времени по индексу [3]
    current_expiry_seconds = user_data[4] if (user_data and len(user_data) > 4 and user_data[4] is not None) else 0
    
    current_time_seconds = int(time.time())
    seconds_to_add = days * 24 * 60 * 60
    
    # Если подписка активна -> плюсуем сверху. Если истекла/нет -> считаем от сейчас
    if current_expiry_seconds > current_time_seconds:
        new_expiry_seconds = current_expiry_seconds + seconds_to_add
    else:
        new_expiry_seconds = current_time_seconds + seconds_to_add
        
    new_expiry_ms = new_expiry_seconds * 1000  # Переводим в мс для 3X-UI панелей

    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
        for srv in SERVERS:
            try:
                # Динамически собираем email под конкретную страну
                email_for_panel = f"{srv['country_flag']}_{srv['country_name']}_#{user_id}".replace(" ", "_")
                
                # 1. Авторизация на конкретной панели
                login_url = f"{srv['panel_url']}{srv['base_path']}/login"
                async with session.post(login_url, data={"username": srv['panel_user'], "password": srv['panel_password']}, timeout=10) as resp:
                    await resp.text()

                headers = {"Accept": "application/json"}

                # 2. Получение текущих данных инбаунда, чтобы узнать UUID и subId клиента
                get_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/get/{srv['inbound_id']}"
                async with session.get(get_url, headers=headers, timeout=10) as resp:
                    res_json = await resp.json()
                    
                if not res_json.get("success"):
                    logging.error(f"Не удалось получить данные инбаунда на сервере {srv['id']}: {res_json}")
                    continue

                settings = json.loads(res_json["obj"]["settings"])
                clients = settings.get("clients", [])
                
                # Ищем клиента по tgId или email
                current_client = next((c for c in clients if c.get("tgId") == user_id), None)
                if not current_client:
                    old_email = f"user_{user_id}"
                    current_client = next((c for c in clients if c.get("email") == old_email), None)

                # Если клиента на этой панели физически нет, создаем его через ваш чистый метод
                if not current_client:
                    await get_vpn_config_clean(user_id, username)
                    # Перезапрашиваем данные
                    async with session.get(get_url, headers=headers, timeout=10) as r_retry:
                        res_json = await r_retry.json()
                    settings = json.loads(res_json["obj"]["settings"])
                    current_client = next((c for c in settings.get("clients", []) if c.get("tgId") == user_id), None)

                if not current_client:
                    logging.error(f"Не удалось найти/создать клиента {user_id} на сервере {srv['id']}")
                    continue

                client_uuid = current_client.get("id")
                sub_id = current_client.get("subId", secrets.token_hex(8))

                # 3. Отправляем обновление с новым expiryTime на панель
                update_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/updateClient/{client_uuid}"
                client_data = {
                    "id": str(srv['inbound_id']),
                    "settings": json.dumps({"clients": [{
                        "id": client_uuid,
                        "email": email_for_panel,
                        "limitIp": current_client.get("limitIp", 2),
                        "totalGB": current_client.get("totalGB", 0),
                        "expiryTime": new_expiry_ms, # Наш новый рассчитанный срок
                        "enable": True,              # Принудительно включаем
                        "tgId": user_id,
                        "subId": sub_id  
                    }]})
                }
                async with session.post(update_url, headers=headers, data=client_data, timeout=10) as r:
                    await r.text()

                logging.info(f"Сервер {srv['id']} успешно продлен на {days} дн. для {user_id}")

            except Exception as e:
                logging.error(f"Ошибка гибкого продления на сервере {srv['id']}: {e}")
                continue

    # ---- 4. Обновление локальной БД Amvera и синхронизация с сайтом ----
    try:
        # Перегенерируем чистые ссылки с учетом новых сроков
        vless_links, _ = await get_vpn_config_clean(user_id, username)
        combined_configs = "\n".join(vless_links) if vless_links else ""
        base64_payload = base64.b64encode(combined_configs.strip().encode('utf-8')).decode('utf-8')
        
        # Токен подписки по вашему стандарту
        sub_id_db = "e" + hashlib.md5(str(user_id).encode()).hexdigest()[:15]
        
        # Обновляем сайт, чтобы ссылка sonatavpn.ru сразу отдавала новые данные
        await send_sub_to_website(sub_id_db, base64_payload, new_expiry_seconds)
        
        # Пишем в локальную SQLite3 (в секундах)
        real_username = username or (user_data[0] if user_data else "")
        add_or_update_user(user_id, real_username, combined_configs, sub_id_db, new_expiry_seconds)
    except Exception as db_err:
        logging.error(f"Ошибка финальной записи в БД/Сайт при гибком продлении: {db_err}")
        # Запасной вариант апдейта только времени в БД
        add_or_update_user(user_id, username, None, None, new_expiry_seconds)
        
    return True




async def revoke_vpn_subscription(user_id: int) -> bool:
    """
    Аннулирует подписку на ВСЕХ серверах из списка SERVERS в 3X-UI,
    отключая клиентов и сбрасывая время окончания в локальной БД.
    """
    jar = aiohttp.CookieJar(unsafe=True)
    connector = aiohttp.TCPConnector(ssl=False)
    
    any_server_updated = False

    try:
        async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
            for srv in SERVERS:
                try:
                    # Динамически формируем email под конкретный сервер
                    email_for_panel = f"{srv['country_flag']}_{srv['country_name']}_#{user_id}".replace(" ", "_")
                    
                    # 1. Авторизация на конкретной панели
                    login_url = f"{srv['panel_url']}{srv['base_path']}/login"
                    async with session.post(login_url, data={"username": srv['panel_user'], "password": srv['panel_password']}, timeout=10) as resp:
                        await resp.text()

                    headers = {"Accept": "application/json"}

                    # 2. Получаем текущие данные инбаунда
                    get_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/get/{srv['inbound_id']}"
                    async with session.get(get_url, headers=headers, timeout=10) as resp:
                        res_json = await resp.json()

                    if not res_json.get("success"):
                        logging.error(f"Не удалось получить данные инбаунда на сервере {srv['id']}: {res_json}")
                        continue

                    settings = json.loads(res_json["obj"]["settings"])
                    clients = settings.get("clients", [])

                    # Поиск строго по уникальному tgId или по старому email
                    current_client = next((c for c in clients if c.get("tgId") == user_id), None)
                    if not current_client:
                        old_email = f"user_{user_id}"
                        current_client = next((c for c in clients if c.get("email") == old_email), None)

                    if not current_client:
                        logging.warning(f"Клиент {user_id} не найден на сервере {srv['id']}. Пропускаем.")
                        continue

                    client_uuid = current_client['id']
                    update_url = f"{srv['panel_url']}{srv['base_path']}/panel/api/inbounds/updateClient/{client_uuid}"
                    
                    # Переводим в неактивное состояние
                    past_expiry = 1 

                    client_data = {
                        "id": str(srv['inbound_id']),
                        "settings": json.dumps({
                            "clients": [{
                                "id": client_uuid,
                                "email": email_for_panel,
                                "limitIp": current_client.get("limitIp", 2),
                                "totalGB": current_client.get("totalGB", 0),
                                "expiryTime": past_expiry,
                                "enable": False,  # Полностью деактивируем
                                "tgId": user_id,
                                "subId": current_client.get("subId", "")
                            }]
                        })
                    }

                    async with session.post(update_url, headers=headers, data=client_data, timeout=10) as resp:
                        update_resp = await resp.json()

                    if update_resp.get("success", False):
                        logging.info(f"Клиент {user_id} успешно отключен на сервере {srv['id']}.")
                        any_server_updated = True
                    else:
                        logging.error(f"Панель {srv['id']} вернула ошибку при обновлении: {update_resp}")

                except Exception as srv_err:
                    logging.error(f"Ошибка при отзыве подписки на сервере {srv['id']}: {srv_err}")
                    continue

        # Если успешно отключили хотя бы на одном сервере, сбрасываем время подписки в локальной БД Amvera
        if any_server_updated:
            # Получаем текущее имя из БД, чтобы не затереть его пустым значением
            user_data = get_user_from_db(user_id)
            current_username = user_data[0] if user_data else ""
            
            # Обнуляем подписку локально
            add_or_update_user(user_id, current_username, expiry_time=0)
            logging.info(f"Локальная подписка для пользователя {user_id} успешно обнулена.")
            return True
            
        return False

    except Exception as e:
        logging.error(f"Критическая ошибка в revoke_vpn_subscription: {e}")
        return False


@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: types.PreCheckoutQuery):
    # Одобряем платеж со стороны бота
    await pre_checkout_query.answer(ok=True)










from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
import logging

# Замените на ID вашего канала (обязательно с @ для публичных или -100... для приватных)
CHANNEL_ID = "@Sonata_Information" 

async def check_user_subscription(bot: Bot, user_id: int) -> bool:
    """
    Проверяет, подписан ли пользователь на обязательный канал.
    Возвращает True, если подписан, и False, если нет.
    """
    # Создатель, Администраторы и Амбассадоры проходят без проверок
    if user_id == ADMIN_ID:
        return True
        
    user_data = get_user_from_db(user_id)
    if user_data and len(user_data) > 5 and user_data[5] in ["admin", "ambassador"]:
        return True

    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # Разрешенные статусы: участник, администратор, создатель канала
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except TelegramBadRequest as e:
        # Если бот не добавлен в канал как администратор, он не сможет проверить подписку
        logging.error(f"Ошибка проверки подписки: бот не является админом в канале {CHANNEL_ID}. Ошибка: {e}")
        return True  # Пропускаем пользователя, чтобы бот не завис из-за ошибки админа
    except Exception as ex:
        logging.error(f"Критическая ошибка при проверке подписки: {ex}")
        return True






# --- Клавиатуры ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Подключиться (Happ)", callback_data="connect")], 
        [InlineKeyboardButton(text="👤 Личный кабинет", callback_data="cabinet")],
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
        [InlineKeyboardButton(text="🎟 Активировать промокод", callback_data="enter_promo")],
        [InlineKeyboardButton(text="📖 Информация и поддержка", callback_data="info")]
    ])


def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

# --- Хендлеры ---
import time
import asyncio
from aiogram import types
from aiogram.filters import Command, CommandObject

# Секунды в 3 днях
THREE_DAYS_SECONDS = 3 * 24 * 3600

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject = None):
    # === ШАГ 0: МГНОВЕННЫЙ ОТВЕТ ПОЛЬЗОВАТЕЛЮ ===
    # Отправляем сообщение о загрузке, чтобы пользователь видел, что бот работает
    loading_msg = await message.answer("⏳ <b>Загрузка...</b>", parse_mode="HTML")

    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    # 1. Проверяем наличие пользователя в БД ДО каких-либо действий
    existing_user = get_user_from_db(user_id)
    is_new_user = existing_user is None
    
    ref_bonus_text = ""
    
    # 2. Реферальная система (строго для новых пользователей)
    if command and command.args and command.args.startswith("ref") and is_new_user:
        try:
            inviter_id = int(command.args.replace("ref", ""))
            
            # Защита: нельзя пригласить самого себя
            if inviter_id != user_id:
                inviter_data = get_user_from_db(inviter_id)
                
                if inviter_data:
                    # === НАЧИСЛЕНИЕ ПРИГЛАСИВШЕМУ (РЕФЕРЕРУ) ===
                    # Извлекаем текущее время окончания подписки пригласившего (индекс 4 из вашей БД)
                    try:
                        inviter_old_expiry = int(inviter_data[4]) if inviter_data[4] is not None else 0
                    except (ValueError, TypeError):
                        inviter_old_expiry = 0

                    current_time = int(time.time())

                    # Если подписка еще активна, прибавляем к ней, иначе — к текущему времени
                    if inviter_old_expiry > current_time:
                        days_left = (inviter_old_expiry - current_time) / (24 * 3600)
                        days_to_add = int(days_left) + 3
                        await renew_vpn_subscription_flexible(inviter_id, days_to_add)
                    else:
                        await renew_vpn_subscription_flexible(inviter_id, 3)

                    # Уведомление пригласившему
                    try:
                        await message.bot.send_message(
                            chat_id=inviter_id,
                            text=f"🤝 <b>Новый реферал!</b>\n\n"
                                 f"<blockquote>Пользователь @{username} зарегистрировался по вашей ссылке.\n"
                                 f"🎁 Вам начислено: <b>+3 дня подписки</b>!</blockquote>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                    # НАЧИСЛЯЕМ 3 ДНЯ НОВОМУ ПОЛЬЗОВАТЕЛЮ (РЕФЕРАЛУ)
                    add_or_update_user(user_id, username, expiry_time=0)
                    await renew_vpn_subscription_flexible(user_id, 3)

                    # ФИКСИРУЕМ СВЯЗЬ В БД ДЛЯ СЧЕТЧИКА В ЛИЧНОМ КАБИНЕТЕ
                    try:
                        add_referral_connection(inviter_id, user_id)
                    except Exception:
                        pass 
                    
                    ref_bonus_text = (
                        f"<blockquote>🎉 <b>Вам начислен реферальный бонус!</b>\n"
                        f"🎁 Подарочные <b>3 дня подписки</b> уже активированы.</blockquote>\n\n"
                    )

        except (ValueError, TypeError):
            pass

    # 3. Обработка регистрации и обновлений (если не было реферального бонуса)
    if is_new_user and not ref_bonus_text:
        add_or_update_user(user_id, username, expiry_time=0)
    elif not is_new_user:
        try:
            old_expiry = int(existing_user[4]) if existing_user[4] is not None else 0
        except (ValueError, TypeError):
            old_expiry = 0
            
        add_or_update_user(user_id, username, expiry_time=old_expiry, role=existing_user[5])

    # === ШАГ 4: УДАЛЕНИЕ СООБЩЕНИЯ О ЗАГРУЗКЕ ===
    # Все тяжелые запросы в X-UI панель и БД завершены. Удаляем «Загрузка...»
    try:
        await loading_msg.delete()
    except Exception:
        pass

    # 5. Отправка главного сообщения (видео)
    final_caption = f"{ref_bonus_text}{text1}"
    
    await message.answer_video(
        video=VIDEO_MAIN,  
        caption=final_caption,
        reply_markup=main_kb(), 
        parse_mode="HTML"
    )






@dp.callback_query(F.data == "enter_promo")
async def enter_promo_callback(callback: types.CallbackQuery):
    await callback.answer()
    
    text = (
        "🎟 <b>Активация промокода Sonata VPN</b>\n\n"
        "Чтобы активировать промокод, отправьте его в чат с командой <code>/promo</code>.\n\n"
        "<b>Пример ввода:</b>\n"
        "<code>/promo ВАШ_ПРОМОКОД</code> (нажмите, чтобы скопировать)"
    )
    
    # Кнопка возврата в главное меню
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])
    
    if callback.message.caption:
        await callback.message.edit_caption(caption=text, reply_markup=back_kb, parse_mode="HTML")
    else:
        await callback.message.edit_text(text=text, reply_markup=back_kb, parse_mode="HTML")





@dp.callback_query(F.data == "cabinet")
async def cabinet(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    # Генерация реферальной ссылки
    try:
        bot_info = await callback.bot.get_me()
        ref_url = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    except Exception:
        ref_url = f"https://t.me/bot?start=ref{user_id}"

    # НОВОЕ: Получаем количество приглашенных пользователей за всё время
    # Обязательно добавьте функцию get_user_invite_count в ваш файл с БД
    invite_count = get_user_invite_count(user_id)

    # ИСПРАВЛЕНО: Добавлен счетчик рефералов прямо под ссылкой
    ref_text_block = (
        f"🤝 <b>Партнерская программа:</b>\n"
        f"Приглашайте друзей по ссылке и получайте бонусы!\n"
        f"🔗 Ссылка: <code>{ref_url}</code>\n"
        f"👥 Приглашено друзей: <b>{invite_count}</b> чел.\n\n"
    )

    # Запрашиваем словарь из исправленной БД
    db_data = get_user_from_db(user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    # Проверяем, что запись найдена и в ней достаточно полей (минимум до expiry_time)
    if db_data and len(db_data) > 4:
        # Извлекаем роль из индекса 5 (если поле NULL или отсутствует, ставим 'user')
        db_role = db_data[5] if len(db_data) > 5 and db_data[5] is not None else "user"
        

        # Задаем статус создателя
        if user_id == ADMIN_ID:
            role = "creator"
        else:
            role = db_role

        # Настройка текстовых плашек с нужными вам цветами
        if role == "creator":
            role_badge = "<blockquote><b>Статус:</b> 🟢БОРЗ (Владелец)</blockquote>"
            is_premium_role = True
        elif role == "admin":
            role_badge = "<blockquote><b>Статус:</b> 🔴Администратор (Staff)</blockquote>"
            is_premium_role = True
        elif role == "ambassador":
            role_badge = "<blockquote><b>Статус:</b> 🟠Амбассадор (Partner)</blockquote>"
            is_premium_role = True
        else:
            role_badge = "<blockquote><b>Статус:</b> 🔵Пользователь</blockquote>"
            is_premium_role = False

        # 3. Извлекаем время подписки по правильному индексу 4
        expiry_timestamp = db_data[4] if db_data[4] is not None else 0
        current_time = time.time()
        
        days_left = 0
        if expiry_timestamp > current_time:
            days_left = int((expiry_timestamp - current_time) / (24 * 3600))

        # ИСПРАВЛЕНО: Если у человека больше 3000 дней или он является стаффом — пишем БЕЗЛИМИТ
        if days_left > 3000 or is_premium_role:
            status_text = "<b>🟢 ∞ Безлимитная подписка</b>"
            has_access = True
        elif days_left > 0:
            status_text = f"🟢 Активна (осталось {days_left} дн.)"
            has_access = True
        else:
            status_text = "🔴 Не активна (требуется оплата)"
            has_access = False

        # Сборка итогового сообщения
        text = (
            f"<b>👤 Личный кабинет</b>\n\n"
            f"{role_badge}\n"
            f"<b>ID пользователя:</b> <code>{user_id}</code>\n"
            f"<b>Статус подписки:</b> {status_text}\n\n"
            f"{ref_text_block}"
        )

        if has_access:
            text += "✨ Ваша подписка активна! Чтобы подключить устройство или обновить настройки, перейдите в главное меню бота и нажмите кнопку <b>«Подключиться»</b>."
            kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
        else:
            text += "⚠️ Для получения доступа к высокоскоростному VPN Sonata, пожалуйста, приобретите подписку или активируйте промокод."
            kb.inline_keyboard.append([InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")])
            kb.inline_keyboard.append([InlineKeyboardButton(text="🎟 Активировать промокод", callback_data="enter_promo")])
            kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    else:
        text = "❌ Ошибка профиля. Нажмите /start для перезапуска бота."
        kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])

    try:
        if callback.message.caption:
            await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
        else:
            await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass








#@dp.callback_query(F.data == "connect")
#async def connect(callback: types.CallbackQuery):
#   await callback.answer()
#   
#    user_id = callback.from_user.id
#    username = callback.from_user.username or ""    
    # 1. Запускаем нашу проверку подписки
#    is_subscribed = await check_user_subscription(callback.bot, user_id)
    
#    if not is_subscribed:
        # Если пользователь не подписан, прерываем логику и выдаем блокирующее окно
#        await callback.answer("⚠️ Требуется подписка!")
        
        # Получаем прямую ссылку на канал для кнопки
#        channel_username = CHANNEL_ID.replace("@", "")
#        channel_url = f"https://t.me/{channel_username}"
        
        # Кнопка проверки и кнопка перехода в канал
#        kb = InlineKeyboardMarkup(inline_keyboard=[
#            [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_url)],
            # Важно: callback_data должна вести на этот же хэндлер ("connect"), 
            # чтобы при повторном нажатии после подписки пользователя сразу пропустило дальше!
#            [InlineKeyboardButton(text="🔄 Я подписался (Проверить)", callback_data="connect")]
#        ])
        
#        text = (
#            "🔒 <b>Требуется подписка на канал</b>\n\n"
#            "<blockquote>Для доступа к подписке, пожалуйста, подпишитесь на наш официальный канал.\n\n"
#            "Там мы публикуем важные обновления, информацию и промокоды.😉</blockquote>"
#        )
        
#        try:
#            if callback.message.caption:
#                await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")
#            else:
#                await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
#        except Exception:
#            pass
#        return  # Завершаем выполнение, не давая скачать VPN-конфиг

    # 1. Проверяем статус подписки перед генерацией
#    db_data = get_user_from_db(user_id)
#    current_time = time.time()
    
#    try:
#        expiry_in_db = int(db_data[5]) if (db_data and len(db_data) > 5 and db_data[5] is not None) else 0
#    except (ValueError, TypeError):
#        expiry_in_db = 0
    
    # ВРЕМЕННО ОТКЛЮЧЕНО ДЛЯ ТЕСТИРОВАНИЯ
    # if expiry_in_db <= current_time:
    #     kb_no_access = InlineKeyboardMarkup(inline_keyboard=[
    #         [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy")],
    #         [InlineKeyboardButton(text="🎟 Активировать промокод", callback_data="enter_promo")],
    #         [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    #     ])
    #     text_no_access = "🔒 <b>Доступ ограничен</b>\n\nУ вас нет активной подписки."
    #     if callback.message.caption:
    #         await callback.message.edit_caption(caption=text_no_access, reply_markup=kb_no_access, parse_mode="HTML")
    #     else:
    #         await callback.message.edit_text(text=text_no_access, reply_markup=kb_no_access, parse_mode="HTML")
    #     return

#    loading_text = "⏳ <b>Синхронизация серверов и формирование вашей подписки...</b>"
#    try:
#        if callback.message.caption:
#            await callback.message.edit_caption(caption=loading_text, reply_markup=None, parse_mode="HTML")
#        else:
#            await callback.message.edit_text(text=loading_text, reply_markup=None, parse_mode="HTML")
#    except Exception as e:
#        logging.warning(f"Не удалось обновить сообщение на статус загрузки: {e}")

#    try:
#        vless_links, expiry_time_ms = await get_vpn_config_clean(user_id, username)
        
#        sub_id = "e" + hashlib.md5(str(user_id).encode()).hexdigest()[:15]
        
        # ИСПРАВЛЕНО СТРОГО ПО ВАШЕЙ СТРУКТУРЕ: Убраны фигурные скобки вокруг переменной
#        auto_connect_url = f"https://sonatavpn.ru" + "/" + str(sub_id) + "?auto=1"

        # Склеиваем ссылки строго через перенос строки (\n) для базы данных
#        combined_configs = "\n".join(vless_links) if vless_links else ""
#        base64_payload = base64.b64encode(combined_configs.strip().encode('utf-8')).decode('utf-8')

#        expiry_seconds = int(expiry_time_ms / 1000) if expiry_time_ms > 0 else int(expiry_in_db)
#        if expiry_seconds == 0:
#            expiry_seconds = int(time.time() + 2592000)
            
#        expiry_date = datetime.fromtimestamp(expiry_seconds).strftime('%d.%m.%Y в %H:%M')

#        debug_servers_info = ""
#        for link in vless_links:
#            if "#" in link:
#                server_name = urllib.parse.unquote(link.split("#")[-1]).strip()
#            else:
#                server_name = "Доступный узел"
#            debug_servers_info += f"✅ {server_name} — <b>Успешно подключен</b>\n"

#        if not vless_links:
#            debug_servers_info = "❌ <b>Ни одна нода не ответила!</b> Проверьте логи.\n"

#        kb = InlineKeyboardMarkup(inline_keyboard=[
#            [InlineKeyboardButton(text="⚡️ ИМПОРТИРОВАТЬ В HAPP", url=auto_connect_url)],
#            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
#        ])

#        text = (
#            f"🚀 <b>РЕЖИМ ОТЛАДКИ Sonata VPN</b>\n\n"
#            f"📅 Срок действия: до <b>{expiry_date}</b>\n"
#            f"🔗 Ссылка импорта: <code>{auto_connect_url}</code>\n\n"
#            f"<b>Статус синхронизации нод:</b>\n"
#            f"{debug_servers_info}\n"
#            f"Нажмите кнопку ниже для автоматического импорта конфигураций всех доступных стран в ваше приложение Happ."
#        )

        # Проверяем реальный статус для сайта, не отключая режим отладки в ТГ
#        if expiry_seconds <= int(time.time()):
            # Если подписка РЕАЛЬНО просрочена прямо сейчас (новое время вышло)
#            asyncio.create_task(send_sub_to_website(sub_id, "", expiry_seconds))
#            logging.info(f"[ОТЛАДКА] Пользователь {user_id} действительно просрочен. На сайт ушла пустота.")
#        else:
            # Если подписка активна (новое время больше текущего)
#            asyncio.create_task(send_sub_to_website(sub_id, base64_payload, expiry_seconds))
#            logging.info(f"[ОТЛАДКА] Пользователь {user_id} активен до {expiry_date}. Конфиги отправлены.")
            
#        add_or_update_user(user_id, username, combined_configs, sub_id, expiry_seconds)


#        try:
#            await callback.message.delete()
#        except Exception:
#            pass
            
#        await callback.message.answer(text=text, reply_markup=kb, parse_mode="HTML")
            
#    except Exception as e:
#        logging.error(f"Критическая ошибка в connect: {e}", exc_info=True)
#        try:
#            await callback.message.answer("⚠️ Произошла внутренняя ошибка бота при генерации.")
#        except Exception:
#            pass







@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer()
    
    user_id = callback.from_user.id
    username = callback.from_user.username or ""    
    
    # 1. Проверка подписки на канал
    is_subscribed = await check_user_subscription(callback.bot, user_id)
    if not is_subscribed:
        await callback.answer("⚠️ Требуется подписка!")
        channel_username = CHANNEL_ID.replace("@", "")
        channel_url = f"https://t.me/{channel_username}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_url)],
            [InlineKeyboardButton(text="🔄 Я подписался (Проверить)", callback_data="connect")]
        ])
        text = (
            "🔒 <b>Требуется подписка на канал</b>\n\n"
            "<blockquote>Для доступа к подписке, пожалуйста, подпишитесь на наш официальный канал.\n\n"
            "Там мы публикуем важные обновления, информацию и промокоды.😉</blockquote>"
        )
        try:
            await callback.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")
        except Exception: pass
        return

    # 2. Получаем данные из БД (Имитируем структуру: предполагаем, что вы допишете получение сохраненной ОС и Приложения)
    db_data = get_user_from_db(user_id)
    saved_os = db_data[8] if (db_data and len(db_data) > 8) else None
    saved_app = db_data[9] if (db_data and len(db_data) > 9) else None

    
    # Если пользователь УЖЕ выбирал устройство ранее — пускаем без лишних вопросов!
    if saved_os and saved_app:
        await callback.message.answer("⏳ Формирование и синхронизация...") # Или сразу вызов Шага 3
        # Формируем callback вручную или перенаправляем на финальную генерацию
        await process_final_screen(callback, user_id, username, db_data, saved_os, saved_app)
        return

    # 3. Если зашел ВПЕРВЫЕ (данных нет) -> Показываем выбор ОС
    kb_os = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🍏 iPhone / iPad", callback_data="set_os_ios"),
            InlineKeyboardButton(text="🤖 Android", callback_data="set_os_and")
        ],
        [
            InlineKeyboardButton(text="🪟 Windows", callback_data="set_os_win"),
            InlineKeyboardButton(text="💻 macOS", callback_data="set_os_mac")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

    text_os = (
        "💻 <b>Выберите ваше устройство</b>\n\n"
        "Пожалуйста, выберите операционную систему, на которую вы хотите установить VPN. "
        "Мы запомним ваш выбор, чтобы не спрашивать в следующий раз. 😉"
    )
    try:
        await callback.message.edit_text(text=text_os, reply_markup=kb_os, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text=text_os, reply_markup=kb_os, parse_mode="HTML")






@dp.callback_query(F.data.startswith("save_"))
async def save_user_preferences(callback: types.CallbackQuery):
    await callback.answer()
    
    # Разбираем callback_data (например: save_ios_happ)
    _, selected_os, selected_app = callback.data.split("_")
    user_id = callback.from_user.id
    username = callback.from_user.username or ""
    
    save_user_device_prefs(user_id, selected_os, selected_app)

    logging.info(f"Пользователь {user_id} сохранил выбор: ОС={selected_os}, Приложение={selected_app}")
    
    db_data = get_user_from_db(user_id)
    await process_final_screen(callback, user_id, username, db_data, selected_os, selected_app)


# Выносим генерацию экрана в отдельную функцию, чтобы вызывать её и при повторном входе
async def process_final_screen(callback: types.CallbackQuery, user_id, username, db_data, selected_os, selected_app):
    # Генерация конфигов (ваш оригинальный код)
    vless_links, expiry_time_ms = await get_vpn_config_clean(user_id, username)
    sub_id = "e" + hashlib.md5(str(user_id).encode()).hexdigest()[:15]
    
    combined_configs = "\n".join(vless_links) if vless_links else ""
    base64_payload = base64.b64encode(combined_configs.strip().encode('utf-8')).decode('utf-8')

    try:
        expiry_in_db = int(db_data[5]) if (db_data and len(db_data) > 5 and db_data[5] is not None) else 0
    except (ValueError, TypeError):
        expiry_in_db = 0

    expiry_seconds = int(expiry_time_ms / 1000) if expiry_time_ms > 0 else int(expiry_in_db)
    if expiry_seconds == 0:
        expiry_seconds = int(time.time() + 2592000)
        
    expiry_date = datetime.fromtimestamp(expiry_seconds).strftime('%d.%m.%Y в %H:%M')
    
    # Отправка на сайт и апдейт БД основных данных
    if expiry_seconds <= int(time.time()):
        asyncio.create_task(send_sub_to_website(sub_id, "", expiry_seconds))
    else:
        asyncio.create_task(send_sub_to_website(sub_id, base64_payload, expiry_seconds))
        
    add_or_update_user(user_id, username, combined_configs, sub_id, expiry_seconds)

    # Список нод для дебага
    debug_servers_info = ""
    for link in vless_links:
        if "#" in link:
            server_name = urllib.parse.unquote(link.split("#")[-1]).strip()
        else:
            server_name = "Доступный узел"
        debug_servers_info += f"✅ {server_name} — <b>Успешно подключен</b>\n"

    if not vless_links:
        debug_servers_info = "❌ <b>Ни одна нода не ответила!</b>\n"

    # ФОРМИРУЕМ ССЫЛКУ. Передаем в PHP и ОС, и конкретное приложение!
    auto_connect_url = f"https://sonatavpn.ru{sub_id}?auto=1&os={selected_os}&app={selected_app}"

    # КНОПКА «Новое устройство» ведет на хэндлер очистки reset_device
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚡️ Импортировать в {selected_app.upper()}", url=auto_connect_url)],
        [InlineKeyboardButton(text="🔄 Подключить другое устройство", callback_data="reset_device")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])

    text = (
        f"🚀 <b>РЕЖИМ ОТЛАДКИ Sonata VPN</b>\n\n"
        f"📱 Устройство: <b>{selected_os.upper()}</b> | Клиент: <b>{selected_app.upper()}</b>\n"
        f"📅 Срок действия: до <b>{expiry_date}</b>\n"
        f"🔗 Ссылка импорта: <code>{auto_connect_url}</code>\n\n"
        f"<b>Статус синхронизации нод:</b>\n"
        f"{debug_servers_info}\n"
        f"Нажмите кнопку ниже для импорта настроек."
    )

    try:
        await callback.message.delete()
    except Exception: pass
        
    await callback.message.answer(text=text, reply_markup=kb, parse_mode="HTML")


# Хэндлер сброса настроек устройства
@dp.callback_query(F.data == "reset_device")
async def reset_device_preferences(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    
    clear_user_device_prefs(user_id)

    
    # После очистки вызываем заново хэндлер connect, который запустит опрос сначала!
    await connect(callback)











from aiogram.filters import Command

@dp.callback_query(F.data == "back")
async def back_to_main_menu(callback: types.CallbackQuery):
    await callback.answer()
    
    text = (
        "<b>👋 Привет, добро пожаловать в наш VPN сервис</b>\n\n"
        "🖥️ У нас доступны локации: Европейские страны, а также Белые Списки\n\n"
        "📖 Выберите действие:"
    )
    
    # 1. Сначала удаляем текущее сообщение (кабинет или коннектор), чтобы очистить чат
    try:
        await callback.message.delete()
    except Exception:
        pass  # Если сообщение старое и удалить нельзя, просто идем дальше
        
    # 2. Отправляем главное меню заново точно так же, как в команде /start
    try:
        await callback.message.answer_video(
            video=VIDEO_MAIN,  # Используется ваша переменная с file_id или URL видео
            caption=text,
            reply_markup=main_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Ошибка отправки видео при возврате в меню: {e}")
        # Запасной вариант: если видео упадет (как из-за кривого file_id), отправляем хотя бы текст с кнопками
        await callback.message.answer(
            text=text,
            reply_markup=main_kb(),
            parse_mode="HTML"
        )



from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

@dp.callback_query(F.data == "info")
async def info(callback: types.CallbackQuery):
    await callback.answer()
    text = (
        "<b>Поддержка:</b> @Sonata_VPN_Admin\n"
        "<b>Канал:</b> https://t.me/Sonata_Information\n\n"
        "<i>Информация будет обновляться</i>"
    )
    
    # Создаем клавиатуру с кнопкой Нагрузки и кнопкой Назад
    info_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Нагрузка серверов", callback_data="server_status")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")] # Замените "back" на реальный callback вашей кнопки назад, если он другой
    ])
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=info_kb, parse_mode="HTML")
    except Exception:
        pass




@dp.callback_query(F.data == "server_status")
async def server_status(callback: types.CallbackQuery):
    await callback.answer("Получаю данные от серверов...")
    
    # ИСПРАВЛЕНО: Передаем конкретные объекты серверов из вашего глобального списка SERVERS
    load_fi = await fetch_real_server_load(SERVERS[0])  # Финляндия (fi_1)
    load_pl = await fetch_real_server_load(SERVERS[1])  # Польша (de_1)
    load_ru = await fetch_real_server_load(SERVERS[2])  # Обход №1 (ru_bridge_1)
    
    def get_status_text(load):
        if load is None:
            return "⚪️ Недоступен"
        
        if load < 40:
            return f"{load}% — 🟢 Стабильно"
        elif load < 75:
            return f"{load}% — 🟡 Умеренно"
        else:
            return f"{load}% — 🔴 Загружен"

    status_text = (
        "<b>📊 Актуальная нагрузка на сервера:</b>\n\n"
        f"🇫🇮 <b>Финляндия:</b> {get_status_text(load_fi)}\n"
        f"🇵🇱 <b>Польша:</b> {get_status_text(load_pl)}\n"
        f"🇷🇺 <b>Обход №1:</b> {get_status_text(load_ru)}\n\n"
        "<i>Данные обновляются в реальном времени. Если сервер загружен, рекомендуем переключиться на другой.</i>"
    )
    
    back_to_info_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="info")]
    ])
    
    try:
        await callback.message.edit_caption(caption=status_text, reply_markup=back_to_info_kb, parse_mode="HTML")
    except Exception:
        pass






@dp.callback_query(F.data == "buy")
async def subscription(callback: types.CallbackQuery):
    await callback.answer()
    
    # ИСПРАВЛЕНО: Добавлены новые кнопки для тарифов на 3 и 5 месяцев
    buy_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 1 месяц — 150 руб.", callback_data="pay_30_days")],
        [InlineKeyboardButton(text="💳 3 месяца — 350 руб.", callback_data="pay_90_days")],
        [InlineKeyboardButton(text="💳 5 месяцев — 650 руб.", callback_data="pay_150_days")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])
    
    try:
        await callback.message.edit_caption(
            caption=(
                "Выбор тарифа:\n\n"
                "Оплатите подписку, чтобы снять ограничения по времени работы ваших VPN-ключей.\n\n"
                "📖 Доступные варианты подписки:"
            ),
            reply_markup=buy_kb,
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass

# 1 МЕСЯЦ (Остался без изменений)
@dp.callback_query(F.data == "pay_30_days")
async def send_invoice_30(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    await get_vpn_config_clean(callback.from_user.id, callback.from_user.username or "")
    logging.info(f"Диспетчер: Отправка инвойса 30 дней пользователю {callback.from_user.id}")
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Подписка на VPN (30 дней)",
        description="Прoдление доступа к подписке VPN Sonata на 1 месяц.",
        payload="vpn_30_days_subscription",
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="1 месяц подписки", amount=15000)], # 150.00 RUB
        start_parameter="vpn-sub-30-days"
    )

# 3 МЕСЯЦА (ДОБАВЛЕНО)
@dp.callback_query(F.data == "pay_90_days")
async def send_invoice_90(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    await get_vpn_config_clean(callback.from_user.id, callback.from_user.username or "")
    logging.info(f"Диспетчер: Отправка инвойса 90 дней пользователю {callback.from_user.id}")
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Подписка на VPN (3 месяца)",
        description="Продление доступа к подписке VPN Sonata на 3 месяца.",
        payload="vpn_90_days_subscription", # Изменен payload для отслеживания при оплате
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="3 месяца подписки", amount=35000)], # 350.00 RUB в копейках
        start_parameter="vpn-sub-90-days"
    )

# 5 МЕСЯЦЕВ (ДОБАВЛЕНО)
@dp.callback_query(F.data == "pay_150_days")
async def send_invoice_150(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    await get_vpn_config_clean(callback.from_user.id, callback.from_user.username or "")
    logging.info(f"Диспетчер: Отправка инвойса 150 дней пользователю {callback.from_user.id}")
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Подписка на VPN (5 месяцев)",
        description="Продление доступа к подписке VPN Sonata на 5 месяцев.",
        payload="vpn_150_days_subscription", # Изменен payload для отслеживания при оплате
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="5 месяцев подписки", amount=65000)], # 650.00 RUB в копейках
        start_parameter="vpn-sub-150-days"
    )




@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    # Получаем payload, который мы указывали при создании инвойса
    payload = message.successful_payment.invoice_payload
    logging.info(f"💳 [ПЛАТЕЖ] Успешная оплата от {user_id}. Payload: {payload}")
    
    # Определяем количество дней в зависимости от купленного тарифа
    days_to_add = 0
    tariff_name = ""
    
    if payload == "vpn_30_days_subscription":
        days_to_add = 30
        tariff_name = "1 месяц"
    elif payload == "vpn_90_days_subscription":
        days_to_add = 90
        tariff_name = "3 месяца"
    elif payload == "vpn_150_days_subscription":
        days_to_add = 150
        tariff_name = "5 месяцев"
        
    if days_to_add > 0:
        try:
            # Начисляем дни на ВСЕ сервера и синхронизируем с БД/Сайтом
            await renew_vpn_subscription_flexible(user_id=user_id, days=days_to_add, username=username)
            
            # Получаем обновленную дату для вывода пользователю
            user_data = get_user_from_db(user_id)
            updated_expiry = user_data[3] if (user_data and len(user_data) > 3) else 0
            expiry_date = datetime.fromtimestamp(updated_expiry).strftime('%d.%m.%Y %H:%M')
            
            await message.answer(
                f"🎉 <b>Оплата прошла успешно!</b>\n\n"
                f"📦 Тариф: <b>{tariff_name} (+{days_to_add} дн.)</b>\n"
                f"📅 Подписка продлена до: <b>{expiry_date}</b>\n\n"
                f"<i>✨ Сервера обновлены. Вы можете зайти в меню «Подключиться» и обновить конфигурацию. Спасибо, что вы с нами!</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Ошибка при начислении дней после оплаты для {user_id}: {e}", exc_info=True)
            await message.answer(
                "⚠️ <b>Оплата получена, но произошел сбой обновления серверов.</b>\n"
                "Пожалуйста, перешлите этот чек администратору, вам активируют подписку вручную.",
                parse_mode="HTML"
            )
    else:
        logging.error(f"Неизвестный payload платежа: {payload}")
        await message.answer("⚠️ Произошла ошибка: неизвестный тип подписки.")




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


from aiogram import types
from aiogram.filters import Command

@dp.message(Command("gift"), IsAdmin())
async def admin_gift_sub(message: types.Message):
    try:
        parts = message.text.split()
        target_user_id = int(parts[1])  
        days_to_add = int(parts[2])     
    except (IndexError, ValueError):
        await message.answer(
            "⚠️ <b>Неверный формат!</b> Пишите так:\n"
            "<code>/gift ID_ПОЛЬЗОВАТЕЛЯ ДНИ</code>\n\n"
            "Пример: <code>/gift 584930211 5</code>",
            parse_mode="HTML"
        )
        return

    await message.answer(f"⏳ Связываюсь с панелью X-UI для выдачи подписки на {days_to_add} дн. пользователю {target_user_id}...")

    # Вызываем функцию гибкого продления
    sub_id = await renew_vpn_subscription_flexible(target_user_id, days_to_add)
    
    if sub_id:
        conn = sqlite3.connect(DB_PATH); conn.cursor().execute("UPDATE users SET actions_gift = actions_gift + 1 WHERE user_id = ?", (message.from_user.id,)); conn.commit(); conn.close()
        await get_vpn_config_clean(target_user_id)
        
        # Выводим только подтверждение без лишних ссылок
        await message.answer(
            f"🎉 <b>Успех! Подписка выдана.</b>\n\n"
            f"<blockquote>👤 Пользователь: {target_user_id}\n"
            f"⏳ Продлено на: {days_to_add} дней\n"
            f"🟢 Статус: Успешно обновлено в X-UI</blockquote>",
            parse_mode="HTML"
        )
        
        try:
            await message.bot.send_message(
                chat_id=target_user_id,
                text=f"🎁 <b>Вам подарок от администратора!</b>\n"
                     f"Ваша подписка успешно активирована на {days_to_add} дней. Проверьте ваш Личный кабинет!",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await message.answer("❌ <b>Ошибка X-UI панели:</b> Не удалось продлить подписку. Убедитесь, что пользователь нажал /start и существует в панели.")


@dp.message(Command("revoke"), IsAdmin())
async def admin_revoke_sub(message: types.Message):
    try:
        parts = message.text.split()
        target_user_id = int(parts[1])
    except (IndexError, ValueError):
        await message.answer("⚠️ <b>Неверный формат!</b> Пишите так:\n<code>/revoke ID_ПОЛЬЗОВАТЕЛЯ</code>", parse_mode="HTML")
        return

    await message.answer(f"⏳ Отзываю подписку у пользователя {target_user_id} в панели X-UI...")

    success = await revoke_vpn_subscription(target_user_id)
    
    if success:
        await message.answer(
            f"🛑 <b>Доступ аннулирован!</b>\n\n"
            f"<blockquote>👤 Пользователь: {target_user_id}\n"
            f"🔴 Статус: Подписка досрочно завершена\n"
            f"🔒 Доступ: Заблокирован в панели X-UI</blockquote>",
            parse_mode="HTML"
        )
        
        try:
            await message.bot.send_message(
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
    username = message.from_user.username or ""
    payload = message.successful_payment.invoice_payload

    # 1. Определение тарифа
    days_to_add = 0
    tariff_name = ""

    if payload == "vpn_30_days_subscription":
        days_to_add = 30
        tariff_name = "30 дней"
    elif payload == "vpn_90_days_subscription":
        days_to_add = 90
        tariff_name = "3 месяца"
    elif payload == "vpn_150_days_subscription":
        days_to_add = 150
        tariff_name = "5 месяцев"

    if days_to_add == 0:
        logging.error(f"Неизвестный payload платежа: {payload} от пользователя {user_id}")
        return

    # 2. Продление подписки в БД
    success = True
    try:
        loops = days_to_add // 30
        for _ in range(loops):
            res = await renew_vpn_subscription(user_id)
            if not res:
                success = False
    except Exception as e:
        logging.error(f"Ошибка при вызове renew_vpn_subscription для {user_id}: {e}")
        success = False

    try:
        # 3. Фоновая сборка данных подписки (без вывода ключей на экран)
        vless_links, expiry_time_ms = await get_vpn_config_clean(user_id, username)
        
        sub_id = "e" + hashlib.md5(str(user_id).encode()).hexdigest()[:15]
        sub_web_url = "https://sonatavpn.ru" + "/" + str(sub_id)
        auto_connect_url = "https://sonatavpn.ru" + "/" + str(sub_id) + "?auto=1"

        combined_configs = "\n".join(vless_links) if vless_links else ""
        base64_payload = base64.b64encode(combined_configs.strip().encode('utf-8')).decode('utf-8')
        expiry_seconds = int(expiry_time_ms / 1000) if expiry_time_ms > 0 else 1893456000

        # Кнопка по вашему запросу
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Импорт в Happ", url=auto_connect_url)]
        ])

        if success:
            text = (
                f"🎉 <b>Спасибо, что выбираете наш сервис!</b>\n\n"
                f"Оплата прошла успешно, ваша подписка продлена на <b>{tariff_name}</b>.\n\n"
                f"🔗 <b>Ваша постоянная ссылка подписки:</b>\n"
                f"<code>{sub_web_url}</code>\n\n"
                f"👇 Нажмите кнопку ниже для быстрой настройки приложения."
            )
        else:
            text = (
                f"⚠️ <b>Оплата прошла успешно, но возник сбой синхронизации!</b>\n"
                f"Не переживайте, ваш платеж зафиксирован. Подписка на <b>{tariff_name}</b> будет активирована администратором вручную в ближайшее время.\n\n"
                f"🔗 <b>Ваша ссылка для настройки:</b> <code>{sub_web_url}</code>\n"
                f"🆔 Ваш ID для поддержки: <code>{user_id}</code>"
            )

        # 4. Пересылка данных на сайт и запись в БД Amvera
        asyncio.create_task(send_sub_to_website(sub_id, base64_payload, expiry_seconds))
        add_or_update_user(user_id, username, combined_configs, sub_id, expiry_seconds)

        await message.answer(text=text, reply_markup=kb, parse_mode="HTML")

    except Exception as e:
        logging.error(f"Критическая ошибка в обработчике успешного платежа: {e}", exc_info=True)
        await message.answer("⚠️ Оплата прошла успешно, но при генерации ссылки возникла ошибка. Пожалуйста, обратитесь в поддержку.")




import time
import asyncio
import sqlite3
import logging

async def check_and_notify_expiring_subscriptions(bot):
    """
    Фоновая задача: запускается раз в день.
    Проверяет пользователей строго по индексам вашей БД: row[0] - user_id, row[1] - expiry_time
    """
    logging.info("⏳ Запуск проверки статусов и истекающих подписок...")
    
    current_time = int(time.time())
    
    # Интервал для уведомления за 3 дня (от 48 до 72 часов до конца подписки)
    three_days_min = current_time + (2 * 24 * 3600)
    three_days_max = current_time + (3 * 24 * 3600)
    
    # Интервал для уведомления об окончании (истекла за последние 24 часа)
    expired_min = current_time - (24 * 3600)
    expired_max = current_time
    
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0) 
        cursor = conn.cursor()
        
        # Выбираем ID и время окончания для проверки за 3 дня
        cursor.execute(
            "SELECT user_id, expiry_time FROM users WHERE expiry_time >= ? AND expiry_time <= ?", 
            (three_days_min, three_days_max)
        )
        expiring_rows = cursor.fetchall()  # Получаем список строк вида [(8679920181, 1787652280), ...]
        
        # Выбираем ID и время окончания для тех, у кого закончилась
        cursor.execute(
            "SELECT user_id, expiry_time FROM users WHERE expiry_time >= ? AND expiry_time <= ?",
            (expired_min, expired_max)
        )
        expired_rows = cursor.fetchall()
        
        conn.close()
    except Exception as e:
        logging.error(f"❌ Ошибка при чтении БД для уведомлений: {e}")
        return

    # --- БЛОК 1: УВЕДОМЛЕНИЕ ЗА 3 ДНЯ ---
    for row in expiring_rows:
        user_id = row[0]  # Первый столбец из выборки
        try:
            text = (
                "⚠️ <b>Внимание!</b>\n\n"
                "Ваша VPN-подписка заканчивается через <b>3 дня</b>.\n"
                "Пожалуйста, продлите её вовремя, чтобы не потерять доступ к сети."
            )
            await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
            logging.info(f"🔔 Уведомление (3 дня) отправлено пользователю {user_id}")
            await asyncio.sleep(0.05)  # Защита от лимитов Telegram API
            
        except Exception as err:
            logging.error(f"Не удалось отправить уведомление за 3 дня пользователю {user_id}: {err}")

    # --- БЛОК 2: УВЕДОМЛЕНИЕ ОБ ОКОНЧАНИИ ---
    for row in expired_rows:
        user_id = row[0]  # Первый столбец из выборки
        try:
            text = (
                "🛑 <b>Срок действия подписки истек!</b>\n\n"
                "Ваш VPN-доступ временно отключен.\n"
                "Чтобы восстановить безопасное подключение, перейдите в главное меню и оплатите продление."
            )
            await bot.send_message(chat_id=user_id, text=text, parse_mode="HTML")
            logging.info(f"🛑 Уведомление об отключении отправлено пользователю {user_id}")
            await asyncio.sleep(0.05)
            
        except Exception as err:
            logging.error(f"Не удалось отправить уведомление об окончании пользователю {user_id}: {err}")


async def scheduler(bot):
    """Цикл, который запускает проверку раз в сутки под именем scheduler."""
    # Даем боту 10 секунд на полную инициализацию после старта скрипта
    await asyncio.sleep(10)
    
    while True:
        try:
            # Вызываем нашу обновленную функцию проверки подписок
            await check_and_notify_expiring_subscriptions(bot)
        except Exception as e:
            logging.error(f"Критическая ошибка в планировщике подписок: {e}")
        
        # Засыпаем ровно на 24 часа до следующей проверки
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


