# =====================================================================
# 🎁 ПРОБНЫЙ ПЕРИОД + ФОНОВАЯ АНТИНАКРУТКА  (отдельный модуль trial_block.py)
#
# Подключение в основном файле бота (3 строки):
#   1) вверху, рядом с другими import:      import trial_block
#   2) в main(), после tg_widgets.setup():  trial_block.setup(globals())
#   3) в main(), рядом с create_task:       asyncio.create_task(trial_block.trial_sweep_loop(bot))
# и в конце process_captcha:
#       if not ref_bonus_text:
#           asyncio.create_task(trial_block.trial_offer(callback.from_user))
#
# Логика:
#  1. Новый пользователь прошёл капчу -> считаем «балл подозрительности».
#  2. Балл низкий  -> пробник выдаётся сразу, человек ничего не замечает.
#  3. Балл высокий -> просим подтвердить e-mail (один e-mail = один аккаунт), потом выдаём пробник.
#  4. Фон (каждые 10 мин): если с одного IP подключились TRIAL_IP_MAX_ACCOUNTS+ пробных аккаунтов —
#     пробник снимается и просим подтвердить почту.
# =====================================================================
import asyncio
import base64
import datetime as _dt
import hashlib
import html as _html
import logging
import re
import sqlite3
import time
import urllib.parse

from aiogram import F, Router, types
from aiogram.enums.button_style import ButtonStyle
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
try:
    from aiogram.types import CopyTextButton      # aiogram 3.13+ (Bot API 7.11+)
except ImportError:                                 # старая версия — кнопка копирования просто не покажется
    CopyTextButton = None

router = Router()

# Всё, что модуль берёт из основного файла бота (подставляется в setup)
_NEEDED = [
    "bot", "dp", "ADMIN_ID", "DB_PATH", "EMAIL_CODE_TTL",
    "get_user_from_db", "renew_vpn_subscription_flexible", "revoke_vpn_subscription", "fetch_user_data_from_vps",
    "email_verify_active", "normalize_email", "is_disposable_email", "mask_email",
    "rv_send_allowed", "rv_issue_code", "rv_log_send", "rv_drop_code", "rv_get_active_code", "rv_check_code",
    "send_code_email", "_rv_kb", "_rv_wait_text", "_rv_conn", "_ret_date",
    "get_vpn_config_clean", "send_sub_to_website", "add_or_update_user", "send_screen", "ret_human",
]

TR_KB_CANCEL = None
TR_KB_CODE = None


def setup(g: dict):
    """Вызвать один раз в main(): trial_block.setup(globals())"""
    missing = [n for n in _NEEDED if n not in g]
    if missing:
        raise RuntimeError(f"[TRIAL] В основном файле не найдено: {', '.join(missing)}")
    globals().update({n: g[n] for n in _NEEDED})
    global TR_KB_CANCEL, TR_KB_CODE
    TR_KB_CANCEL = _rv_kb([("❌ Отмена", "trial:cancel")])
    TR_KB_CODE = _rv_kb([("🔁 Отправить код снова", "trial:resend")],
                        [("✏️ Изменить почту", "trial:change"), ("❌ Отмена", "trial:cancel")])
    g["dp"].include_router(router)
    g["process_final_screen"] = process_final_screen   # новый экран «Подключиться» с режимами
    logging.info("[TRIAL] Модуль пробного периода подключён")


TRIAL_ENABLED = True
TRIAL_DAYS = 4
TRIAL_RISK_THRESHOLD = 3          # балл >= порога -> нужна почта
TRIAL_BURST_10MIN = 6             # столько новых аккаунтов за 10 мин = волна регистраций
TRIAL_IP_MAX_ACCOUNTS = 3         # столько пробных аккаунтов с одного IP = накрутка
TRIAL_SWEEP_SECONDS = 600
TRIAL_NEW_ID_FROM = 0             # 0 = выключено. Если поставить, например, 8500000000 — ID выше (свежие аккаунты) +1 балл

# Веса сигналов (подстройте под себя)
TRIAL_W_NO_PHOTO = 2
TRIAL_W_NO_USERNAME = 1
TRIAL_W_COMMON_NAME = 1           # только имя из списка и без фамилии
TRIAL_W_BURST = 2
TRIAL_W_PREMIUM = -1              # Telegram Premium — доверие выше

TRIAL_COMMON_NAMES = {
    "владимир", "фёдор", "федор", "александр", "алексей", "дмитрий", "иван", "сергей", "андрей", "максим",
    "артем", "артём", "никита", "егор", "михаил", "николай", "данил", "даниил", "кирилл", "илья", "роман",
    "денис", "павел", "олег", "антон", "юрий", "игорь", "виктор", "евгений", "анна", "мария", "елена",
    "ольга", "наталья", "ирина", "екатерина", "анастасия", "дарья", "юлия", "полина", "светлана",
    "vladimir", "ivan", "alex", "alexander", "dmitry", "max", "andrey", "sergey", "user", "test",
}

_TR_READY = False


def _tr_db():
    global _TR_READY
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    if not _TR_READY:
        cur = conn.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS trial_claims (
            user_id INTEGER PRIMARY KEY, score INTEGER, signals TEXT, status TEXT,
            created_ts INTEGER, granted_ts INTEGER, expiry_ts INTEGER, email_norm TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS trial_ips (
            user_id INTEGER, ip TEXT, seen_ts INTEGER, PRIMARY KEY (user_id, ip))''')
        cur.execute('CREATE INDEX IF NOT EXISTS idx_trial_ips_ip ON trial_ips(ip)')
        conn.commit()
        _TR_READY = True
    return conn


def trial_get(user_id: int):
    conn = _tr_db()
    try:
        r = conn.execute('SELECT status, score, granted_ts, expiry_ts FROM trial_claims WHERE user_id=?', (user_id,)).fetchone()
        return {"status": r[0], "score": r[1], "granted_ts": r[2], "expiry_ts": r[3]} if r else None
    finally:
        conn.close()


def trial_set(user_id: int, **fields):
    if not fields:
        return
    conn = _tr_db()
    try:
        cols = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f'UPDATE trial_claims SET {cols} WHERE user_id=?', (*fields.values(), user_id))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- ОЦЕНКА РИСКА
async def trial_risk(user: types.User):
    """Возвращает (балл, список сигналов). Бот НЕ видит IP/устройство из Telegram — их проверяет фоновый sweep."""
    score, signals = 0, []

    try:
        photos = await bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count == 0:
            score += TRIAL_W_NO_PHOTO
            signals.append("no_photo")
    except Exception:
        pass    # не смогли узнать — не наказываем

    if not user.username:
        score += TRIAL_W_NO_USERNAME
        signals.append("no_username")

    first = (user.first_name or "").strip().lower()
    if first in TRIAL_COMMON_NAMES and not (user.last_name or "").strip():
        score += TRIAL_W_COMMON_NAME
        signals.append("common_name")

    if TRIAL_NEW_ID_FROM and user.id >= TRIAL_NEW_ID_FROM:
        score += 1
        signals.append("new_account")

    if getattr(user, "is_premium", False):
        score += TRIAL_W_PREMIUM
        signals.append("premium")

    conn = _tr_db()
    try:
        n = conn.execute('SELECT COUNT(*) FROM trial_claims WHERE created_ts>?', (int(time.time()) - 600,)).fetchone()[0]
    finally:
        conn.close()
    if n >= TRIAL_BURST_10MIN:
        score += TRIAL_W_BURST
        signals.append(f"burst_{n}")

    return score, signals


# ---------------------------------------------------------------- ВЫДАЧА ПРОБНИКА
def _trial_connect_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📲 Подключиться", callback_data="connect", style=ButtonStyle.PRIMARY)]])


async def trial_grant(user_id: int, username: str, status: str = "granted") -> bool:
    ok = False
    try:
        ok = await renew_vpn_subscription_flexible(user_id, TRIAL_DAYS, username)
    except Exception as e:
        logging.error(f"[TRIAL] Ошибка выдачи пробника {user_id}: {e}", exc_info=True)
    row = get_user_from_db(user_id)
    try:
        expiry = int(row[4]) if row and row[4] is not None else 0
    except (ValueError, TypeError):
        expiry = 0
    if ok:
        trial_set(user_id, status=status, granted_ts=int(time.time()), expiry_ts=expiry)
        try:
            await bot.send_message(
                user_id,
                f"🎁 <b>Вам начислен пробный период — {TRIAL_DAYS} дня!</b>\n\n"
                f"<blockquote>Подписка активна до <b>{_ret_date(expiry)}</b> (МСК). Нажмите «Подключиться», выберите устройство — и VPN работает.</blockquote>",
                parse_mode="HTML", reply_markup=_trial_connect_kb())
        except Exception:
            pass
    else:
        logging.error(f"[TRIAL] Пробник для {user_id} не применился на панелях")
        try:
            await bot.send_message(ADMIN_ID, f"⚠️ Пробник не выдался пользователю <code>{user_id}</code> — смотрите лог [TRIAL]/[RENEW].", parse_mode="HTML")
        except Exception:
            pass
    return ok


async def trial_ask_email(user_id: int, reason_text: str = None):
    text = reason_text or (
        f"🎁 <b>Пробный период {TRIAL_DAYS} дня</b>\n\n"
        "Чтобы получить пробник, подтвердите e-mail — это защита от массовых фейковых аккаунтов. "
        "Займёт меньше минуты: пришлём 6-значный код на почту.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📧 Подтвердить почту и получить пробник", callback_data="trial:start")]])
    try:
        await bot.send_message(user_id, text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logging.warning(f"[TRIAL] Не удалось отправить запрос почты {user_id}: {e}")


async def trial_offer(user: types.User):
    """Вызывать один раз после регистрации нового пользователя (после капчи)."""
    if not TRIAL_ENABLED:
        return
    uid = user.id
    if trial_get(uid):
        return
    username = user.username or f"user_{uid}"
    score, signals = await trial_risk(user)
    need_email = score >= TRIAL_RISK_THRESHOLD and email_verify_active()

    conn = _tr_db()
    try:
        conn.execute('INSERT OR IGNORE INTO trial_claims (user_id, score, signals, status, created_ts) VALUES (?,?,?,?,?)',
                     (uid, score, ",".join(signals), "need_email" if need_email else "pending", int(time.time())))
        conn.commit()
    finally:
        conn.close()
    logging.info(f"[TRIAL] {uid}: score={score} signals={signals} -> {'email' if need_email else 'auto'}")

    if need_email:
        await trial_ask_email(uid)
    else:
        await trial_grant(uid, username, "granted")


# ---------------------------------------------------------------- ПОДТВЕРЖДЕНИЕ ПОЧТЫ
class TrialMail(StatesGroup):
    waiting_email = State()
    waiting_code = State()




def _tr_needs_email(user_id: int) -> bool:
    c = trial_get(user_id)
    return bool(c and c["status"] == "need_email")


@router.callback_query(F.data == "trial:start")
async def trial_cb_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not _tr_needs_email(callback.from_user.id):
        await callback.message.answer("ℹ️ Пробный период уже получен или недоступен.")
        return
    await state.set_state(TrialMail.waiting_email)
    await callback.message.answer("📧 Пришлите адрес вашей почты — отправлю на неё 6-значный код.\n<i>Один e-mail — один аккаунт.</i>",
                                  parse_mode="HTML", reply_markup=TR_KB_CANCEL)


@router.callback_query(F.data == "trial:cancel")
async def trial_cb_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except Exception: pass
    await callback.message.answer("Хорошо. Получить пробник можно позже — просто нажмите /trial.")


@router.message(Command("trial"))
async def trial_cmd(message: types.Message):
    if _tr_needs_email(message.from_user.id):
        await trial_ask_email(message.from_user.id)
    else:
        await message.answer("ℹ️ Для вашего аккаунта нет доступного пробного периода.")


@router.callback_query(F.data == "trial:change")
async def trial_cb_change(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    rv_drop_code(callback.from_user.id)
    await state.set_state(TrialMail.waiting_email)
    await callback.message.answer("✏️ Пришлите другой адрес.", reply_markup=TR_KB_CANCEL)


async def _tr_send_code(message: types.Message, state: FSMContext, user_id: int, email: str, email_norm: str, resend=False):
    ok, reason, wait = rv_send_allowed(user_id, email_norm)
    if not ok:
        await message.answer(_rv_wait_text(reason, wait), parse_mode="HTML", reply_markup=TR_KB_CODE if reason in ("cooldown", "hour_limit") else TR_KB_CANCEL)
        return
    code = rv_issue_code(user_id, email, email_norm)
    if not await send_code_email(email, code):
        rv_drop_code(user_id)
        await message.answer("⚠️ Не удалось отправить письмо. Проверьте адрес и попробуйте чуть позже.", reply_markup=TR_KB_CANCEL)
        await state.set_state(TrialMail.waiting_email)
        return
    rv_log_send(user_id, email_norm)
    await state.set_state(TrialMail.waiting_code)
    prefix = "🔁 Новый код отправлен.\n\n" if resend else ""
    await message.answer(
        f"{prefix}✉️ Код отправлен на <code>{_html.escape(mask_email(email))}</code>\n\n"
        f"Введите <b>6 цифр</b> из письма. Код действует {EMAIL_CODE_TTL // 60} минут.\n<i>Не пришло? Проверьте «Спам».</i>",
        parse_mode="HTML", reply_markup=TR_KB_CODE)


@router.callback_query(F.data == "trial:resend")
async def trial_cb_resend(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    active = rv_get_active_code(callback.from_user.id)
    if not active:
        await state.set_state(TrialMail.waiting_email)
        await callback.message.answer("Пришлите e-mail ещё раз.", reply_markup=TR_KB_CANCEL)
        return
    await _tr_send_code(callback.message, state, callback.from_user.id, active["email"], active["email_norm"], resend=True)


@router.message(TrialMail.waiting_email, F.text, ~F.text.startswith("/"))
async def trial_receive_email(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not _tr_needs_email(uid):
        await state.clear()
        await message.answer("ℹ️ Пробный период уже получен или недоступен.")
        return
    parsed = normalize_email(message.text)
    if not parsed:
        await message.answer("❌ Это не похоже на e-mail. Пример: <code>name@gmail.com</code>", parse_mode="HTML", reply_markup=TR_KB_CANCEL)
        return
    email, email_norm = parsed
    if is_disposable_email(email_norm):
        await message.answer("❌ Временные почты не подходят. Укажите свой постоянный e-mail.", reply_markup=TR_KB_CANCEL)
        return
    await _tr_send_code(message, state, uid, email, email_norm)


def _tr_bind_email(user_id: int, email_norm: str) -> bool:
    """Атомарно привязывает почту к аккаунту. False — почта уже занята другим."""
    _tr_db().close()
    _rv_conn().close()
    conn = sqlite3.connect(DB_PATH, timeout=30.0, isolation_level=None)
    try:
        cur = conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        cur.execute('SELECT user_id FROM verified_emails WHERE email_norm=?', (email_norm,))
        owner = cur.fetchone()
        if owner and int(owner[0]) != int(user_id):
            cur.execute("ROLLBACK")
            return False
        cur.execute('INSERT OR IGNORE INTO verified_emails (email_norm, user_id, verified_at) VALUES (?,?,?)', (email_norm, user_id, int(time.time())))
        cur.execute("UPDATE trial_claims SET email_norm=? WHERE user_id=?", (email_norm, user_id))
        cur.execute("COMMIT")
        return True
    except Exception as e:
        try: cur.execute("ROLLBACK")
        except Exception: pass
        logging.error(f"[TRIAL] Ошибка привязки почты {user_id}: {e}")
        return False
    finally:
        conn.close()


@router.message(TrialMail.waiting_code, F.text, ~F.text.startswith("/"))
async def trial_receive_code(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    code = re.sub(r"\D", "", message.text or "")
    if len(code) != 6:
        await message.answer("Введите <b>6 цифр</b> из письма.", parse_mode="HTML", reply_markup=TR_KB_CODE)
        return
    if not _tr_needs_email(uid):
        await state.clear()
        await message.answer("ℹ️ Пробный период уже получен или недоступен.")
        return

    status, extra = rv_check_code(uid, code)
    if status == "wrong":
        await message.answer(f"❌ Неверный код. Осталось попыток: <b>{extra}</b>.", parse_mode="HTML", reply_markup=TR_KB_CODE)
        return
    if status in ("locked", "expired", "none"):
        await state.set_state(TrialMail.waiting_email)
        await message.answer({"locked": "🔒 Слишком много неверных попыток — код аннулирован.",
                              "expired": "⌛ Срок действия кода истёк.",
                              "none": "ℹ️ Активного кода нет."}[status] + "\nПришлите e-mail ещё раз, чтобы получить новый код.",
                             reply_markup=TR_KB_CANCEL)
        return

    rv_drop_code(uid)
    await state.clear()
    if not _tr_bind_email(uid, extra):
        await message.answer("❌ Эта почта уже привязана к другому аккаунту. Нажмите /trial и укажите другой адрес.")
        return
    await trial_grant(uid, message.from_user.username or f"user_{uid}", "verified")


@router.message(TrialMail.waiting_email, ~F.text)
@router.message(TrialMail.waiting_code, ~F.text)
async def trial_wrong_input(message: types.Message):
    await message.answer("Отправьте текстом: e-mail или код из письма.")


# ---------------------------------------------------------------- ФОНОВАЯ ПРОВЕРКА ПО IP
def _tr_ip_ok(ip: str) -> bool:
    ip = (ip or "").strip()
    return bool(ip) and not ip.startswith(("10.", "192.168.", "127.", "0.", "172.16.", "fe80", "::1"))


async def trial_sweep(bot_):
    now = int(time.time())
    conn = _tr_db()
    try:
        rows = conn.execute("SELECT user_id, expiry_ts FROM trial_claims WHERE status='granted' AND granted_ts>?", (now - 72 * 3600,)).fetchall()
    finally:
        conn.close()

    for uid, claim_expiry in rows:
        user = get_user_from_db(uid)
        sub_id = user[3] if user and len(user) > 3 else None
        if not sub_id:
            continue
        data = await fetch_user_data_from_vps(sub_id)
        if not data or data.get("status") != "success":
            continue
        ips = {d.get("ip") for d in (data.get("devices") or []) if _tr_ip_ok(d.get("ip"))}
        if not ips:
            continue

        conn = _tr_db()
        try:
            for ip in ips:
                conn.execute('INSERT OR REPLACE INTO trial_ips (user_id, ip, seen_ts) VALUES (?,?,?)', (uid, ip, now))
            conn.commit()
            shared = 0
            for ip in ips:
                n = conn.execute(
                    "SELECT COUNT(DISTINCT t.user_id) FROM trial_ips t JOIN trial_claims c ON c.user_id=t.user_id "
                    "WHERE t.ip=? AND c.granted_ts>?", (ip, now - 7 * 86400)).fetchone()[0]
                shared = max(shared, n)
        finally:
            conn.close()

        if shared < TRIAL_IP_MAX_ACCOUNTS:
            continue

        # Если человек уже что-то купил/продлил — не трогаем
        try:
            cur_expiry = int(user[4] or 0)
        except (ValueError, TypeError):
            cur_expiry = 0
        if cur_expiry > int(claim_expiry or 0) + 3600:
            trial_set(uid, status="verified")
            continue

        logging.warning(f"[TRIAL] {uid}: {shared} пробных аккаунтов с одного IP — снимаю пробник, нужна почта")
        await revoke_vpn_subscription(uid)
        trial_set(uid, status="need_email")
        await trial_ask_email(uid,
            "🛡 <b>Нужно подтверждение</b>\n\n"
            "Мы заметили много пробных аккаунтов с одного подключения, поэтому пробный период приостановлен. "
            "Если вы обычный пользователь — подтвердите e-mail, и он сразу вернётся.")
        await asyncio.sleep(0.5)


async def trial_sweep_loop(bot_):
    await asyncio.sleep(60)
    while True:
        try:
            if TRIAL_ENABLED:
                await trial_sweep(bot_)
        except Exception as e:
            logging.error(f"[TRIAL] Ошибка фоновой проверки: {e}", exc_info=True)
        await asyncio.sleep(TRIAL_SWEEP_SECONDS)


# ---------------------------------------------------------------- АДМИН-КОМАНДЫ
@router.message(Command("trial_status"))
async def trial_cmd_status(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = _tr_db()
    try:
        st = dict(conn.execute("SELECT status, COUNT(*) FROM trial_claims GROUP BY status").fetchall())
        avg = conn.execute("SELECT ROUND(AVG(score),2) FROM trial_claims").fetchone()[0]
    finally:
        conn.close()
    await message.answer(
        f"<b>🎁 Пробный период</b> ({'вкл' if TRIAL_ENABLED else 'выкл'}, {TRIAL_DAYS} дн., порог {TRIAL_RISK_THRESHOLD})\n"
        f"Выдано сразу: <b>{st.get('granted', 0)}</b>\nЧерез почту: <b>{st.get('verified', 0)}</b>\n"
        f"Ждут почту: <b>{st.get('need_email', 0)}</b>\nСредний балл риска: <b>{avg}</b>\n\n"
        "Сбросить пробник пользователю: <code>/trial_reset ID</code>", parse_mode="HTML")


@router.message(Command("trial_reset"))
async def trial_cmd_reset(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    if not (command.args or "").strip().isdigit():
        await message.answer("Формат: <code>/trial_reset ID</code>", parse_mode="HTML")
        return
    uid = int(command.args.strip())
    conn = _tr_db()
    try:
        conn.execute("DELETE FROM trial_claims WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM trial_ips WHERE user_id=?", (uid,))
        conn.commit()
    finally:
        conn.close()
    await message.answer(f"✅ Пробник пользователя {uid} сброшен — он снова может его получить.")



# =====================================================================
# 🖥 ЭКРАН ПОСЛЕ ВЫБОРА УСТРОЙСТВА: режимы «представительский» / «тестовый»
#   /mode — переключатель (только для создателя ADMIN_ID)
#   Представительский — красивая карточка подписки (как в «Бабка VPN»).
#   Тестовый — прежний «РЕЖИМ ОТЛАДКИ» со списком нод и ссылкой импорта.
# Настройка общая для всех пользователей, хранится в БД (переживает перезапуск).
# =====================================================================
UI_MODE_DEFAULT = "view"      # "view" — представительский, "test" — тестовый

# Название тарифа берётся из последней покупки (таблица purchases) или из пробного периода
TARIFF_NAMES = {
    "vpn_30_days_subscription": "1 месяц",
    "vpn_90_days_subscription": "3 месяца",
    "vpn_150_days_subscription": "5 месяцев",
    "vpn_365_days_subscription": "1 год",
}

OS_TITLES = {"ios": "iPhone / iPad", "and": "Android", "win": "Windows", "mac": "macOS", "lin": "Linux",
             "atv": "Apple TV", "antv": "Android TV"}

_UI_READY = False


def _ui_db():
    global _UI_READY
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    if not _UI_READY:
        conn.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()
        _UI_READY = True
    return conn


def get_ui_mode() -> str:
    conn = _ui_db()
    try:
        r = conn.execute("SELECT value FROM bot_settings WHERE key='ui_mode'").fetchone()
    finally:
        conn.close()
    return r[0] if r and r[0] in ("view", "test") else UI_MODE_DEFAULT


def set_ui_mode(mode: str):
    conn = _ui_db()
    try:
        conn.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('ui_mode', ?)", (mode,))
        conn.commit()
    finally:
        conn.close()


def _mode_text(mode: str) -> str:
    cur = "👔 <b>Представительский</b>" if mode == "view" else "🧪 <b>Тестовый</b>"
    return (f"🖥 <b>Режим экрана «Подключиться»</b>\n\nСейчас: {cur}\n\n"
            "👔 <b>Представительский</b> — аккуратная карточка подписки для пользователей.\n"
            "🧪 <b>Тестовый</b> — отладка: статус нод, ссылка импорта.")


def _mode_kb(mode: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=("✅ " if mode == "view" else "") + "👔 Представительский", callback_data="uimode:view")],
        [InlineKeyboardButton(text=("✅ " if mode == "test" else "") + "🧪 Тестовый", callback_data="uimode:test")],
    ])


@router.message(Command("mode"))
async def ui_mode_cmd(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    arg = (command.args or "").strip().lower()
    if arg in ("view", "test"):
        set_ui_mode(arg)
    mode = get_ui_mode()
    await message.answer(_mode_text(mode), parse_mode="HTML", reply_markup=_mode_kb(mode))


@router.callback_query(F.data.startswith("uimode:"))
async def ui_mode_cb(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав.", show_alert=True)
        return
    mode = callback.data.split(":", 1)[1]
    if mode not in ("view", "test"):
        await callback.answer()
        return
    set_ui_mode(mode)
    await callback.answer("Режим переключён")
    try:
        await callback.message.edit_text(_mode_text(mode), parse_mode="HTML", reply_markup=_mode_kb(mode))
    except Exception:
        pass


def _tariff_label(user_id: int, unlimited: bool) -> str:
    if unlimited:
        return "Безлимит"
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        try:
            p = conn.execute("SELECT payload, days FROM purchases WHERE user_id=? ORDER BY ts DESC LIMIT 1", (user_id,)).fetchone()
            t = conn.execute("SELECT status FROM trial_claims WHERE user_id=?", (user_id,)).fetchone()
        finally:
            conn.close()
    except Exception:
        p, t = None, None
    if p:
        payload, days = p
        if payload in TARIFF_NAMES:
            return TARIFF_NAMES[payload]
        if str(payload).startswith("customdays_"):
            return f"{days} дн."
        return f"{days} дн." if days else "Платный"
    if t and t[0] in ("granted", "verified"):
        return "Пробный"
    return "Бонусный"


def _build_view_text(user_id, db_data, selected_os, selected_app, expiry_seconds, now) -> str:
    role = (db_data[5] if db_data and len(db_data) > 5 and db_data[5] else "user")
    unlimited = (user_id == ADMIN_ID or role in ("creator", "admin", "ambassador", "partner")
                 or (expiry_seconds - now) > 3000 * 86400)

    remaining = expiry_seconds - now
    if unlimited:
        status, date_line = "♾ Безлимитная подписка", "∞ без ограничений"
    elif remaining <= 0:
        status, date_line = "🔴 Подписка не активна", "—"
    else:
        date_line = _dt.datetime.fromtimestamp(expiry_seconds).strftime("%d.%m.%Y")
        status = (f"🟡 Заканчивается через {ret_human(remaining)}" if remaining <= 3 * 86400
                  else f"🟢 Активна, осталось {ret_human(remaining)}")

    tariff = _tariff_label(user_id, unlimited)
    os_title = OS_TITLES.get(selected_os, selected_os.upper())

    return (
        "✨ <b>Ваша подписка</b>\n\n"
        f"<b>{status}</b>\n\n"
        "<blockquote>"
        f"⭐ <b>Тариф:</b> {tariff}\n"
        f"📅 <b>Действует до:</b> {date_line}"
        "</blockquote>\n\n"
        f"💻 <b>Подключение:</b> {os_title} · {selected_app.upper()}\n\n"
        "Нажмите кнопку ниже, чтобы добавить подписку в приложение 👇"
    )


async def process_final_screen(callback: types.CallbackQuery, user_id, username, db_data, selected_os, selected_app):
    """Замена одноимённой функции основного файла (подставляется в setup)."""
    vless_links, expiry_time_ms = await get_vpn_config_clean(user_id, username)
    sub_id = "e" + hashlib.md5(str(user_id).encode()).hexdigest()[:15]

    combined_configs = "\n".join(vless_links) if vless_links else ""
    base64_payload = base64.b64encode(combined_configs.strip().encode("utf-8")).decode("utf-8")

    try:
        expiry_in_db = int(db_data[4]) if (db_data and len(db_data) > 4 and db_data[4] is not None) else 0
    except (ValueError, TypeError, IndexError):
        expiry_in_db = 0

    now = int(time.time())
    expiry_seconds = int(expiry_time_ms / 1000) if expiry_time_ms > 0 else int(expiry_in_db)
    if expiry_seconds <= now:
        expiry_seconds = now
        expiry_date = "❌ Истекла или не приобреталась"
    else:
        expiry_date = _dt.datetime.fromtimestamp(expiry_seconds).strftime("%d.%m.%Y в %H:%M")

    if expiry_seconds <= now:
        asyncio.create_task(send_sub_to_website(sub_id, "", expiry_seconds))
    else:
        asyncio.create_task(send_sub_to_website(sub_id, base64_payload, expiry_seconds))
    add_or_update_user(user_id, username, combined_configs, sub_id, expiry_seconds)

    # ссылка подписки: https://sn-go.ru/<github_raw_url из БД>
    _row = get_user_from_db(user_id)
    sub_token = (_row[3] if _row and len(_row) > 3 and _row[3] else sub_id)
    sub_link = "https://" + "sn-go.ru" + f"/{sub_token}"

    # --- ссылка импорта (логика как в основном файле) ---
    raw_sub_url = "https://" + "sn-go.ru" + f"/{sub_id}?os={selected_os}&app={selected_app}"
    app = selected_app.lower()
    app_scheme = "happ://add/"
    if app == "incy":
        app_scheme = "incy://import/" + urllib.parse.quote(raw_sub_url)
    elif app == "streisand":
        app_scheme = "streisand://import/"
    elif app in ("v2rayng", "v2rayn", "nekobox", "v2rayxs"):
        app_scheme = f"{app}://install-config?url="
    elif app == "karing":
        app_scheme = "karing://install-config?url=" + urllib.parse.quote(raw_sub_url) + "&name=SonataVPN"
    elif app == "singbox":
        app_scheme = "sing-box://import-remote?url=" + urllib.parse.quote(raw_sub_url) + "&name=SonataVPN"
    elif app == "foxray":
        app_scheme = "foxray://import/"

    if app in ("happ", "streisand", "foxray", "v2rayng", "v2rayn", "nekobox", "v2rayxs"):
        auto_connect_url = "https://" + "sn-go.ru" + "/?to=" + urllib.parse.quote(f"{app_scheme}{raw_sub_url}")
    else:
        auto_connect_url = "https://" + "sn-go.ru" + "/?to=" + urllib.parse.quote(app_scheme)

    mode = get_ui_mode()

    rows = [[InlineKeyboardButton(text=f"⚡️ Импортировать в {selected_app.upper()}", url=auto_connect_url, style=ButtonStyle.PRIMARY)]]
    if CopyTextButton is not None:
        rows.append([InlineKeyboardButton(text="📋 Скопировать ссылку", copy_text=CopyTextButton(text=sub_link))])
    if mode == "view":
        rows.append([InlineKeyboardButton(text="💳 Продлить", callback_data="buy", style=ButtonStyle.SUCCESS)])
    rows += [
        [InlineKeyboardButton(text="🖼 Получить QR-код", callback_data=f"showqr_{sub_id}")],
        [InlineKeyboardButton(text="🔄 Выбрать другое устройство", callback_data="reset_device")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    if mode == "view":
        text = _build_view_text(user_id, db_data, selected_os, selected_app, expiry_seconds, now)
    else:
        debug_servers_info = ""
        for link in vless_links:
            name = urllib.parse.unquote(link.split("#")[-1]).strip() if "#" in link else "Доступный узел"
            debug_servers_info += f"✅ {name} — <b>Успешно подключен</b>\n"
        if not vless_links:
            debug_servers_info = "❌ <b>Ни одна нода не ответила!</b>\n"
        text = (
            f"🚀 <b>РЕЖИМ ОТЛАДКИ Sonata VPN</b>\n\n"
            f"📱 Устройство: <b>{selected_os.upper()}</b> | Клиент: <b>{selected_app.upper()}</b>\n"
            f"📅 Срок действия: <b>{expiry_date}</b>\n"
            f"🔗 Ссылка импорта: <code>{auto_connect_url}</code>\n\n"
            f"<b>Статус синхронизации нод:</b>\n"
            f"{debug_servers_info}\n"
            f"Нажмите кнопку ниже для импорта настроек."
        )

    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_screen(callback.message.chat.id, "connect", text, kb)