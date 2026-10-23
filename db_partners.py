import sqlite3
import logging



def init_partner_db():
    """Инициализация всех таблиц партнерской программы"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Таблица партнерских связей (кто под кем зарегистрирован)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS partner_refs (
            user_id INTEGER PRIMARY KEY,           -- ID пришедшего покупателя
            partner_id INTEGER,                     -- ID партнера 1-го уровня (28%)
            sub_partner_id INTEGER,                 -- ID партнера 2-го уровня (9%)
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 2. Таблица статистики, балансов и квестов партнеров
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS partner_stats (
            partner_id INTEGER PRIMARY KEY,
            balance_rub REAL DEFAULT 0.0,           -- Текущий фоновый баланс в рублях
            total_earned REAL DEFAULT 0.0,          -- Сколько всего заработал за всё время
            referrals_count INTEGER DEFAULT 0,      -- Сколько лично пригласил пользователей
            sub_partners_count INTEGER DEFAULT 0,   -- Сколько субпартнеров пригласил
            quest_claimed INTEGER DEFAULT 0         -- Статус квеста на 10 человек
        );
        """)

        # 3. Таблица контроля и логирования заявок на вывод средств
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS partner_withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER,
            amount REAL,
            method TEXT,                            -- 'card' или 'cryptobot'
            credentials TEXT,                       -- Номер карты или юзернейм/кошелек
            status TEXT DEFAULT 'pending',          -- 'pending', 'paid', 'rejected'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        conn.commit()
        conn.close()
        logging.info("🚀 [ПАРТНЕРКА БД] Таблицы партнерской программы успешно проверены/созданы!")
    except Exception as e:
        logging.error(f"❌ Ошибка инициализации БД партнерки: {e}")

# Функция автоматического создания таблиц при первом обращении к модулю
init_partner_db()

def get_partners_for_user(user_id: int):
    """Возвращает (partner_id, sub_partner_id) для конкретного пользователя или (None, None)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT partner_id, sub_partner_id FROM partner_refs WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result if result else (None, None)
    except Exception as e:
        logging.error(f"Ошибка получения партнеров для {user_id}: {e}")
        return None, None

def get_partner_profile(partner_id: int):
    """Возвращает статистику партнера (баланс, заработок, рефералы, квест)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT balance_rub, total_earned, referrals_count, quest_claimed FROM partner_stats WHERE partner_id = ?", (partner_id,))
        row = cursor.fetchone()
        
        if not row:
            cursor.execute("INSERT OR IGNORE INTO partner_stats (partner_id) VALUES (?)", (partner_id,))
            conn.commit()
            cursor.execute("SELECT balance_rub, total_earned, referrals_count, quest_claimed FROM partner_stats WHERE partner_id = ?", (partner_id,))
            row = cursor.fetchone()
            
        conn.close()
        return row
    except Exception as e:
        logging.error(f"Ошибка получения профиля партнера {partner_id}: {e}")
        return 0.0, 0.0, 0, 0

async def add_partner_balance(partner_id: int, amount_coins: float, level: int, from_user_id: int, bot):
    """Фоновое автоматическое начисление баланса партнерам (28% или 9%)"""
    amount_in_rub = amount_coins / 100
    percent = 28 if level == 1 else 9
    bonus_rub = round(amount_in_rub * (percent / 100), 2)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO partner_stats (partner_id) VALUES (?)", (partner_id,))
        cursor.execute("""
            UPDATE partner_stats 
            SET balance_rub = balance_rub + ?, total_earned = total_earned + ? 
            WHERE partner_id = ?
        """, (bonus_rub, bonus_rub, partner_id))
        conn.commit()
        conn.close()
        logging.info(f"💰 [ПАРТНЕРКА ФОН] Начислено +{bonus_rub} руб. партнеру {partner_id}")
    except Exception as e:
        logging.error(f"Ошибка фонового обновления баланса партнера {partner_id}: {e}")

def create_withdrawal_request(partner_id: int, amount: float, method: str, credentials: str):
    """Логирует новую заявку на вывод в базу данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO partner_withdrawals (partner_id, amount, method, credentials) VALUES (?, ?, ?, ?)",
            (partner_id, amount, method, credentials)
        )
        req_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return req_id
    except Exception as e:
        logging.error(f"Ошибка сохранения заявки на вывод в БД: {e}")
        return None

def confirm_withdrawal_db(req_id: int):
    """Списывает деньги с текущего баланса при ручном одобрении выплаты админом"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT partner_id, amount, status FROM partner_withdrawals WHERE id = ?", (req_id,))
        row = cursor.fetchone()
        
        if row and row[2] == 'pending':
            partner_id, amount = row[0], row[1]
            cursor.execute("UPDATE partner_stats SET balance_rub = balance_rub - ? WHERE partner_id = ?", (amount, partner_id))
            cursor.execute("UPDATE partner_withdrawals SET status = 'paid' WHERE id = ?", (req_id,))
            conn.commit()
            conn.close()
            return partner_id, amount
        
        conn.close()
        return None
    except Exception as e:
        logging.error(f"Ошибка подтверждения выплаты в БД: {e}")
        return None

def update_partner_balance_manually(partner_id: int, amount: float):
    """Ручное изменение баланса через админ-команду /setbalance (начисление или списание)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO partner_stats (partner_id) VALUES (?)", (partner_id,))
        
        if amount > 0:
            cursor.execute("""
                UPDATE partner_stats 
                SET balance_rub = balance_rub + ?, total_earned = total_earned + ? 
                WHERE partner_id = ?
            """, (amount, amount, partner_id))
        else:
            cursor.execute("""
                UPDATE partner_stats 
                SET balance_rub = balance_rub + ? 
                WHERE partner_id = ?
            """, (amount, partner_id))
            
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Ошибка ручного изменения баланса партнера {partner_id}: {e}")
        return False
