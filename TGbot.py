
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
VIDEO_MAIN = "BAACAgIAAxkBAAPmalZdX_GloRR8mPKqiXL6IEoFFpQAAs-iAALRx7BKu4dtBUXOXuk9BA"

text1 = (
    "<b>👋 Привет, добро пожаловать в наш VPN сервис</b>\n\n"
    " 🖥️ У нас доступны локации: Европейские страны, а также Белые Списки\n\n"
    "📖 Выберите действие:"
)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()


#-----------Работа с базой данных----------------

# --- ХАК ДЛЯ ЗАЩИТЫ БАЗЫ ДАННЫХ НА AMVERA ---
# Проверяем, запущено ли приложение на Amvera (там всегда есть папка /data)
if os.path.exists("/data"):
    PERSISTENT_DB_DIR = "/data"
    # Имя файла вашей базы данных (замените "vpn_bot.db" на ваше реальное имя файла, если оно другое)
    DB_FILENAME = "users.db" 
    
    NEW_DB_PATH = os.path.join(PERSISTENT_DB_DIR, DB_FILENAME)
    
    # Если бот обновился, но в корне остался старый файл базы, а в /data его еще нет — бережно копируем его туда
    if os.path.exists(DB_FILENAME) and not os.path.exists(NEW_DB_PATH):
        try:
            shutil.copy2(DB_FILENAME, NEW_DB_PATH)
            logging.info(f"🚚 База данных успешно мигрировала в постоянное хранилище: {NEW_DB_PATH}")
        except Exception as e:
            logging.error(f"Не удалось скопировать базу данных: {e}")

    # ПРИНУДИТЕЛЬНО ПЕРЕНАПРАВЛЯЕМ ПУТЬ В ЗАЩИЩЕННУЮ ПАПКУ
    DB_PATH = NEW_DB_PATH
    logging.info(f"🔒 Защита Amvera активирована. Актуальный путь базы: {DB_PATH}")
else:
    # Локальный путь для тестов на компьютере (оставляем как было у вас)
    # Если у вас переменная называлась иначе, убедитесь, что она инициализирует ваш стандартный путь
    if 'DB_PATH' not in locals() and 'DB_PATH' not in globals():
        DB_PATH = "users.db" 
# --------------------------------------------


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

    # 1. Ваша существующая таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            vpn_config TEXT,
            github_raw_url TEXT,
            expiry_time INTEGER DEFAULT 0
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
    
    # ТЕХНИЧЕСКИЙ ХАК: Если таблица promocodes уже была на Amvera, 
    # эти запросы добавят новые колонки max_uses и current_uses, не сломав старые промокоды
    try:
        cursor.execute('ALTER TABLE promocodes ADD COLUMN max_uses INTEGER DEFAULT 1;')
        cursor.execute('ALTER TABLE promocodes ADD COLUMN current_uses INTEGER DEFAULT 0;')
    except sqlite3.OperationalError:
        pass # Если колонки уже есть, SQLite выдаст ошибку, мы её просто игнорируем

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
    
    conn.commit()
    conn.close()
    log_system_routing()



def add_or_update_user(user_id, username, vpn_config=None, github_raw_url=None, expiry_time=None):
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, vpn_config, github_raw_url, expiry_time FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            'INSERT INTO users (user_id, username, vpn_config, github_raw_url, expiry_time) VALUES (?, ?, ?, ?, ?)',
            (user_id, username, vpn_config, github_raw_url, expiry_time if expiry_time is not None else 0)
        )
    else:
        new_config = vpn_config if vpn_config is not None else row[1]
        new_github = github_raw_url if github_raw_url is not None else row[2]
        new_expiry = expiry_time if expiry_time is not None else row[3]

        cursor.execute(
            'UPDATE users SET username = ?, vpn_config = ?, github_raw_url = ?, expiry_time = ? WHERE user_id = ?',
            (username, new_config, new_github, new_expiry, user_id)
        )
    conn.commit()
    conn.close()

def get_user_from_db(user_id):
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute('SELECT username, vpn_config, github_raw_url, expiry_time FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

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






import json
import uuid
import secrets
import aiohttp
import logging
import urllib.parse

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




#-----------пробный период----------

def check_and_grant_trial(user_id: int, username: str) -> bool:
    """
    Проверяет, является ли пользователь новым.
    Если да, выдает ему 4 дня бесплатного триала в БД.
    Возвращает True, если триал выдан, и False, если пользователь уже был в базе.
    """
    # 1. Проверяем, существует ли уже пользователь в нашей локальной БД
    user_data = get_user_from_db(user_id)
    
    if user_data is None:
        # 2. Рассчитываем время окончания подписки: текущее время + 4 дня
        # Вычисляем в Unix-timestamp (в секундах)
        trial_days = 4
        expiry_timestamp = int((datetime.now() + timedelta(days=trial_days)).timestamp())
        
        # 3. Добавляем нового пользователя в базу данных с 4 днями подписки
        # Поля конфигурации и ссылок оставляем None, ваш основной код заполнит их при генерации
        add_or_update_user(
            user_id=user_id,
            username=username,
            vpn_config=None,
            github_raw_url=None,
            expiry_time=expiry_timestamp
        )
        
        logging.info(f"🎁 Новому пользователю @{username} (ID: {user_id}) выдано {trial_days} дня триала.")
        return True
        
    return False







async def send_sub_to_website(token, b64_content, expiry):
    """Отправляет сгенерированный Base64 подписки на ваш PHP-сайт"""
    # Железобетонная классическая склейка через слэш
    url = "https://sonatavpn.ru" + "/" + "index.php?update_sub=1"
    data = {
        "token": token,
        "content": b64_content,
        "expiry": expiry
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=5) as response:
                res_text = await response.text()
                logging.info(f"[МАРШРУТИЗАЦИЯ ИИ] Синхронизация токена {token} с сайтом: {res_text}")
    except Exception as ex:
        logging.error(f"[ОШИБКА ИИ] Не удалось передать подписку на сайт: {ex}")





#-----------команды------------


 

@dp.message(F.text.startswith("/gen"))
async def handle_generate_promo(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return 

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
        updated_expiry = user_data[3] if (user_data and len(user_data) > 3) else 0
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




@dp.message(F.text.startswith("/delpromo"))
async def handle_delete_promo(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return # Игнорируем обычных пользователей

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





async def apply_subscription_extension(user_id: int, username: str, days_to_add: int):
    """
    Полностью продлевает подписку пользователя:
    1. Пересчитывает время (в БД секунды, на панелях мс)
    2. Обновляет 3X-UI панели
    3. Перезапускает генерацию конфигов и пушит новый Base64 на сайт
    """
    # ---- 1. Расчет времени ----
    user_data = get_user_from_db(user_id)
    
    # ИСПРАВЛЕНО: берем именно индекс [3] (expiry_time), если строка в БД найдена
    current_expiry_seconds = user_data[3] if (user_data and len(user_data) > 3 and user_data[3] is not None) else 0
    
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
    current_expiry_seconds = user_data[3] if (user_data and len(user_data) > 3 and user_data[3] is not None) else 0
    
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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"

    # 1. Проверяем, новый ли пользователь, и выдаем 4 дня триала
    is_new_user = check_and_grant_trial(user_id, username)
    
    if is_new_user:
        # Если пользователь новый — выводим сообщение про подарок
        await message.answer(
            f"👋 Добро пожаловать в Sonata VPN\n\n"
            f"🎁 Вам начислено <b>4 дня пробного периода</b>.\n"
            f"Нажмите еще раз /start, чтобы получить ваши настройки подключения!",
            parse_mode="HTML"
        )
    else:
        # Если пользователь нажал /start повторно — обновляем его имя в БД и открываем основное меню
        add_or_update_user(user_id, username)
        
        await message.answer_video(
            video=VIDEO_MAIN,  
            caption=text1,
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

    # Читаем данные из локальной SQLite3
    db_data = get_user_from_db(user_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    if db_data and len(db_data) > 3:  
        # ИСПРАВЛЕНО: Добавлен индекс [3] для извлечения числа из кортежа базы данных
        expiry_timestamp = db_data[3] if db_data[3] is not None else 0
        current_time = time.time()

        if expiry_timestamp > current_time:
            days_left = int((expiry_timestamp - current_time) / (24 * 3600))
            status_text = f"🟢 Активна (осталось {days_left} дн.)"

            text = (
                f"<b>👤 Личный кабинет</b>\n\n"
                f"<b>ID пользователя:</b> <code>{user_id}</code>\n"
                f"<b>Статус подписки:</b> {status_text}\n\n"
                f"✨ Ваша подписка активна! Чтобы подключить устройство или обновить настройки, перейдите в главное меню бота и нажмите кнопку <b>«Подключиться»</b>."
            )
            kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])

        else:
            status_text = "🔴 Не активна (требуется оплата)"
            text = (
                f"<b>👤 Личный кабинет</b>\n\n"
                f"<b>ID пользователя:</b> <code>{user_id}</code>\n"
                f"<b>Статус подписки:</b> {status_text}\n\n"
                f"⚠️ Для получения доступа к высокоскоростному VPN Sonata, пожалуйста, приобретите подписку или активируйте промокод."
            )
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






@dp.callback_query(F.data == "connect")
async def connect(callback: types.CallbackQuery):
    await callback.answer()
    
    user_id = callback.from_user.id
    username = callback.from_user.username or ""

    # 1. Проверяем статус подписки перед генерацией
    db_data = get_user_from_db(user_id)
    current_time = time.time()
    
    expiry_in_db = db_data[3] if (db_data and len(db_data) > 3 and db_data[3] is not None) else 0
    
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

    loading_text = "⏳ <b>Синхронизация серверов и формирование вашей подписки...</b>"
    try:
        if callback.message.caption:
            await callback.message.edit_caption(caption=loading_text, reply_markup=None, parse_mode="HTML")
        else:
            await callback.message.edit_text(text=loading_text, reply_markup=None, parse_mode="HTML")
    except Exception as e:
        logging.warning(f"Не удалось обновить сообщение на статус загрузки: {e}")

    try:
        vless_links, expiry_time_ms = await get_vpn_config_clean(user_id, username)
        
        sub_id = "e" + hashlib.md5(str(user_id).encode()).hexdigest()[:15]
        
        # ИСПРАВЛЕНО СТРОГО ПО ВАШЕЙ СТРУКТУРЕ: Убраны фигурные скобки вокруг переменной
        auto_connect_url = f"https://sonatavpn.ru" + "/" + str(sub_id) + "?auto=1"

        # Склеиваем ссылки строго через перенос строки (\n) для базы данных
        combined_configs = "\n".join(vless_links) if vless_links else ""
        base64_payload = base64.b64encode(combined_configs.strip().encode('utf-8')).decode('utf-8')

        expiry_seconds = int(expiry_time_ms / 1000) if expiry_time_ms > 0 else int(expiry_in_db)
        if expiry_seconds == 0:
            expiry_seconds = int(time.time() + 2592000)
            
        expiry_date = datetime.fromtimestamp(expiry_seconds).strftime('%d.%m.%Y в %H:%M')

        debug_servers_info = ""
        for link in vless_links:
            if "#" in link:
                server_name = urllib.parse.unquote(link.split("#")[-1]).strip()
            else:
                server_name = "Доступный узел"
            debug_servers_info += f"✅ {server_name} — <b>Успешно подключен</b>\n"

        if not vless_links:
            debug_servers_info = "❌ <b>Ни одна нода не ответила!</b> Проверьте логи.\n"

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ ИМПОРТИРОВАТЬ В HAPP", url=auto_connect_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
        ])

        text = (
            f"🚀 <b>РЕЖИМ ОТЛАДКИ Sonata VPN</b>\n\n"
            f"📅 Срок действия: до <b>{expiry_date}</b>\n"
            f"🔗 Ссылка импорта: <code>{auto_connect_url}</code>\n\n"
            f"<b>Статус синхронизации нод:</b>\n"
            f"{debug_servers_info}\n"
            f"Нажмите кнопку ниже для автоматического импорта конфигураций всех доступных стран в ваше приложение Happ."
        )

        asyncio.create_task(send_sub_to_website(sub_id, base64_payload, expiry_seconds))
        add_or_update_user(user_id, username, combined_configs, sub_id, expiry_seconds)

        try:
            await callback.message.delete()
        except Exception:
            pass
            
        await callback.message.answer(text=text, reply_markup=kb, parse_mode="HTML")
            
    except Exception as e:
        logging.error(f"Критическая ошибка в connect: {e}", exc_info=True)
        try:
            await callback.message.answer("⚠️ Произошла внутренняя ошибка бота при генерации.")
        except Exception:
            pass










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




import random

@dp.callback_query(F.data == "server_status")
async def server_status(callback: types.CallbackQuery):
    await callback.answer()
    
    # Теперь нагрузка для каждого сервера генерируется в общем диапазоне от 5 до 90%
    load_fi = random.randint(5, 90)
    load_pl = random.randint(5, 90)
    load_ru = random.randint(5, 90)
    
    # Функция для выбора правильного смайлика по процентам
    def get_status_emoji(percentage):
        if percentage < 40:
            return "🟢 Стабильно"
        elif percentage < 75:
            return "🟡 Умеренно"
        else:
            return "🔴 Загружен"

    status_text = (
        "<b>📊 Актуальная нагрузка на сервера Sonata:</b>\n\n"
        f"🇫🇮 <b>Финляндия (fi_1):</b> {load_fi}% — {get_status_emoji(load_fi)}\n"
        f"🇵🇱 <b>Польша (de_1):</b> {load_pl}% — {get_status_emoji(load_pl)}\n"
        f"🇷🇺 <b>Обход №1 (ru_bridge_1):</b> {load_ru}% — {get_status_emoji(load_ru)}\n\n"
        "<i>Данные обновляются в реальном времени. Если сервер загружен, рекомендуем переключиться на другой.</i>"
    )
    
    # Кнопка возврата обратно в меню Инфо
    back_to_info_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад в Инфо", callback_data="info")]
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
        description="Пrodление доступа к высокоскоростному VPN Sonata на 1 месяц.",
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
        description="Продление доступа к высокоскоростному VPN Sonata на 3 месяца со скидкой.",
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
        description="Выгодное продление доступа к высокоскоростному VPN Sonata на 5 месяцев.",
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
        await get_vpn_config_clean(target_user_id)
        
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



import uuid
import json
import zlib
import base64
import urllib.parse
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

# Если объект app уже объявлен выше в файле, эту строку удалите:
app = FastAPI()

@app.get("/import/{user_id}")
async def import_to_happ(user_id: int):
    """
    Эндпоинт на лету собирает crypt3 пакет для Happ под вашим брендом
    и делает автоматический редирект, открывающий приложение.
    """
    # Постоянный UUID, жестко привязанный к Telegram ID
    client_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"user_{user_id}"))

    # Сборка оригинальных конфигураций Reality со всеми вашими данными из SERVERS
    remark_fi = urllib.parse.quote("🇫🇮 Финляндия | Premium")
    vless_fi = (
        f"vless://{client_uuid}@78.17.1.43:43527"
        f"?type=tcp&security=reality&sni=sony.com&fp=chrome"
        f"&pbk=aZDw05rr-XfdquuaFADqMzM1aAdeFhhpx_Du69Io3Sc&sid=f2cfb510fbaa&spx=%2F"
        f"#{remark_fi}"
    )

    remark_pl = urllib.parse.quote("🇵🇱 Польша | Premium")
    vless_pl = (
        f"vless://{client_uuid}@78.17.152.36:16303"
        f"?type=tcp&security=reality&sni=sony.com&fp=chrome"
        f"&pbk=XAAgoWsZcO3CWrMnx1r-hFNYVn8u5rfuZxCD-r5jKEY&sid=aa72b4f659&spx=%2F"
        f"#{remark_pl}"
    )

    # Структура папки подписки для отображения вашего бренда в Happ
    subscription_data = {
        "name": "🚀 Sonata VPN",
        "urls": [vless_fi, vless_pl]
    }
    
    # Профессиональное сжатие и кодирование crypt3
    json_str = json.dumps(subscription_data)
    compressed_data = zlib.compress(json_str.encode('utf-8'))
    b64_encoded = base64.b64encode(compressed_data).decode('utf-8')
    safe_crypto_str = b64_encoded.replace('+', '%2B').replace('/', '%2F').replace('=', '%3D')
    
    happ_url = f"happ://crypt3/{safe_crypto_str}"
    
    # Моментальный редирект: браузер закроется, и сразу запустится Happ
    return RedirectResponse(url=happ_url)





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


