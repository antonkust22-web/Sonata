# -*- coding: utf-8 -*-
"""
miniapp_api.py — «дверь» из сайта sn-go.ru/miniapp в бота. Кладётся рядом с файлом бота.
Блок в main() (try: import miniapp_api ... configure({...}) ... await miniapp_api.start_server()) у вас уже есть — ОСТАВЬТЕ его.
Сайт (index.php) вызывает эти методы сервер-сервер и передаёт подпись Telegram (initData) — здесь она проверяется ещё раз.
Порт: переменная MINIAPP_PORT (по умолчанию 8081).
"""
import asyncio, hashlib, hmac, inspect, json, logging, os, re, sqlite3, time, urllib.parse
from aiohttp import web

C: dict = {}
HIDDEN = {"vpn_config", "code_hash"}          # секреты, которые не показываем нигде
CMD_ROLES = {
    "gift": ("creator", "admin"), "revoke": ("creator", "admin"), "set_limit": ("creator", "admin"),
    "find_user": ("creator", "admin"), "top": ("creator", "admin"),
    "gen": ("creator", "ambassador"), "delpromo": ("creator", "ambassador"),
    "setrole": ("creator",), "demote": ("creator",), "team": ("creator",), "setpartner": ("creator",),
    "setbalance": ("creator",), "status_db": ("creator",), "start_promo": ("creator",),
    "update_servers": ("creator",), "offer": ("creator",), "ret_status": ("creator",), "ref_email_status": ("creator",),
}
# Описание таблиц и столбцов (что за что отвечает) — показывается в мини-приложении
DOCS = {
 "users": ("Пользователи", {"user_id": "Telegram ID", "username": "Юзернейм", "github_raw_url": "ID подписки (sn-go.ru/<ID>)",
   "expiry_time": "Подписка до", "role": "Роль (user/partner/admin/ambassador)", "actions_gift": "Сколько подписок выдал (админ)",
   "actions_gen": "Сколько промокодов создал", "saved_os": "Выбранная ОС", "saved_app": "Выбранное приложение",
   "device_limit": "Лимит устройств (999 = безлимит)", "active_devices_count": "Устройств сейчас", "is_bot": "1 — это бот, не человек"}),
 "purchases": ("Покупки", {"user_id": "Кто купил", "payload": "Тариф/тип покупки", "days": "Дней", "paid_rub": "Оплачено, ₽",
   "ts": "Когда", "is_first": "1 — первая покупка", "discount_pct": "Скидка, %"}),
 "promocodes": ("Промокоды", {"code": "Код", "days": "Дней за активацию", "max_uses": "Лимит активаций", "current_uses": "Уже активировано"}),
 "promocode_activations": ("Активации промокодов", {"code": "Код", "user_id": "Кто активировал", "activated_at": "Когда"}),
 "promo_actions": ("Общие акции", {"promo_name": "Название акции", "end_time": "Окончание", "is_active": "1 — идёт сейчас"}),
 "user_offers": ("Персональные скидки", {"user_id": "Кому", "offer_key": "Ключ предложения", "percent": "Скидка, %",
   "created_ts": "Выдана", "expires_ts": "Действует до", "used_ts": "Использована (пусто — нет)"}),
 "user_devices": ("Устройства", {"user_id": "Владелец", "ip": "IP", "device_os": "ОС", "vpn_app": "Приложение", "last_seen": "Последняя активность"}),
 "referral_connections": ("Приглашения друзей", {"inviter_id": "Кто пригласил", "referral_id": "Кого пригласили", "created_at": "Когда"}),
 "referral_pending": ("Ожидают подтверждения почты", {"referral_id": "Приглашённый", "inviter_id": "Пригласивший", "inviter_role": "Роль пригласившего",
   "created_at": "Создано", "status": "Статус", "email_norm": "Почта", "verified_at": "Подтверждено", "rewarded_at": "Награда выдана", "inviter_rewarded": "1 — пригласивший получил бонус"}),
 "email_verifications": ("Коды подтверждения почты", {"user_id": "Кто", "email": "Почта", "expires_at": "Код действует до", "attempts": "Попыток", "sent_at": "Отправлен"}),
 "verified_emails": ("Подтверждённые почты", {"email_norm": "Почта", "user_id": "Чья", "verified_at": "Когда"}),
 "email_send_log": ("Журнал отправки писем", {"user_id": "Кому", "email_norm": "Почта", "ts": "Когда"}),
 "partner_refs": ("Привязка клиентов к партнёрам", {"user_id": "Клиент", "partner_id": "Партнёр 1-го уровня (28%)", "sub_partner_id": "Партнёр 2-го уровня (9%)", "registered_at": "Когда"}),
 "partner_stats": ("Партнёры: баланс", {"partner_id": "Партнёр", "balance_rub": "Баланс, ₽", "total_earned": "Заработано всего, ₽",
   "referrals_count": "Клиентов", "sub_partners_count": "Субпартнёров", "quest_claimed": "1 — цель «безлимит» выполнена"}),
 "partner_withdrawals": ("Заявки на вывод", {"partner_id": "Партнёр", "amount": "Сумма, ₽", "method": "Способ", "credentials": "Реквизиты", "status": "pending/paid/rejected", "created_at": "Создана"}),
 "sub_track": ("Отслеживание подписок", {"user_id": "Пользователь", "expiry_time": "Окончание подписки", "first_seen_ts": "Когда увидели", "first_remaining": "Секунд было при старте (для кольца «дней осталось»)"}),
 "user_meta": ("Метаданные пользователей", {"user_id": "Пользователь", "first_seen_ts": "Первый заход", "promos_off": "1 — рассылки акций отключены", "blocked": "1 — заблокировал бота"}),
 "campaign_log": ("Журнал рассылок", {"user_id": "Кому", "campaign_key": "Кампания", "ref_key": "Привязка", "sent_ts": "Отправлено", "kind": "Тип", "skipped": "1 — пропущено"}),
}
USER_COLS = ("user_id", "inviter_id", "referral_id", "partner_id", "sub_partner_id")


# имя команды -> имя функции-хендлера в файле бота
HANDLERS = {"gift": "admin_gift_sub", "revoke": "admin_revoke_sub", "set_limit": "admin_set_device_limit",
            "find_user": "find_user_universal_cmd", "top": "cmd_top_inviters", "gen": "handle_generate_promo",
            "delpromo": "handle_delete_promo", "setrole": "handle_set_role", "demote": "handle_demote_user",
            "team": "handle_show_team", "setpartner": "set_partner_command", "setbalance": "set_balance_command",
            "status_db": "cmd_admin_stats", "start_promo": "start_promo_command", "update_servers": "admin_night_mass_update",
            "offer": "ret_cmd_offer", "ret_status": "ret_cmd_status", "ref_email_status": "rv_cmd_status"}


def configure_from_bot(ns: dict):
    """Вызывать из main() бота:  miniapp_api.configure_from_bot(globals())  — всё нужное берётся из файла бота само."""
    from aiogram.filters import CommandObject
    cmds, missing = {}, []
    for name, fn in HANDLERS.items():
        if fn in ns: cmds[name] = ns[fn]
        else: missing.append(fn)
    if missing: logging.warning(f"[MINIAPP] в боте не найдены хендлеры: {missing}")
    configure({"bot": ns["bot"], "BOT_TOKEN": ns["API_TOKEN"], "DB_PATH": ns["DB_PATH"], "ADMIN_ID": ns["ADMIN_ID"],
               "commands": cmds, "CommandObject": CommandObject, "activate_promo_in_db": ns["activate_promo_in_db"],
               "apply_subscription_extension": ns["apply_subscription_extension"], "get_partner_profile": ns["get_partner_profile"],
               "create_withdrawal_request": ns["create_withdrawal_request"], "confirm_withdrawal_db": ns["confirm_withdrawal_db"],
               "InlineKeyboardMarkup": ns["InlineKeyboardMarkup"], "InlineKeyboardButton": ns["InlineKeyboardButton"]})


def configure(cfg=None, *_ignored):
    if not isinstance(cfg, dict):   # старый вызов configure(bot, dp) падал с «takes 1 positional argument but 2 were given»
        logging.error("[MINIAPP] configure() ждёт dict. Используйте miniapp_api.configure_from_bot(globals())"); return
    C.clear(); C.update(cfg)
    miss = [k for k in ("bot", "BOT_TOKEN", "DB_PATH", "ADMIN_ID", "commands", "CommandObject", "activate_promo_in_db",
                        "apply_subscription_extension", "get_partner_profile", "create_withdrawal_request",
                        "confirm_withdrawal_db", "InlineKeyboardMarkup", "InlineKeyboardButton") if k not in C]
    logging.info("[MINIAPP] API сконфигурировано" + (f", НЕ ХВАТАЕТ ключей: {miss}" if miss else ""))


def q(sql, args=(), one=False):
    conn = sqlite3.connect(C["DB_PATH"], timeout=30.0); conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        return (rows[0] if rows else None) if one else rows
    except sqlite3.Error as e:
        logging.warning(f"[MINIAPP] SQL: {e}"); return None if one else []
    finally:
        conn.close()


def ex(sql, args=()):
    conn = sqlite3.connect(C["DB_PATH"], timeout=30.0)
    try: conn.execute(sql, args); conn.commit()
    finally: conn.close()


def verify(init_data, max_age=172800):
    try:
        p = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True)); got = p.pop("hash", "")
        chk = "\n".join(f"{k}={p[k]}" for k in sorted(p))
        sec = hmac.new(b"WebAppData", C["BOT_TOKEN"].encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(hmac.new(sec, chk.encode(), hashlib.sha256).hexdigest(), got): return None
        if time.time() - int(p.get("auth_date", 0)) > max_age: return None
        return json.loads(p["user"])
    except Exception:
        return None


def role_of(uid):
    if uid == C["ADMIN_ID"]: return "creator"
    r = q("SELECT role FROM users WHERE user_id=?", (uid,), one=True)
    return (r or {}).get("role") or "user"


def err(m): return {"ok": False, "error": m}
def staff(uid, *roles): return role_of(uid) in roles


def tables():
    return [r["name"] for r in q("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def docs_of(name):
    t, cols = DOCS.get(name, (name, {}))
    return {"title": t, "cols": cols}


def clean(rows):
    for r in rows:
        for k in HIDDEN: r.pop(k, None)
    return rows


# ───────────── методы ─────────────
async def m_promo(uid, tg, b):
    code = str(b.get("code") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9_\-]{2,40}", code): return err("Введите корректный промокод")
    res = C["activate_promo_in_db"](code, uid)
    msgs = {"NOT_FOUND": "Такого промокода нет", "YOU_ALREADY_USED": "Вы уже активировали этот промокод", "ALREADY_USED": "Промокод исчерпал лимит активаций"}
    if isinstance(res, str): return err(msgs.get(res, "Не удалось активировать промокод"))
    try:
        await C["apply_subscription_extension"](uid, tg.get("username") or "", int(res))
    except Exception as e:
        logging.error(f"[MINIAPP] промо: {e}", exc_info=True); return err("Промокод принят, но подписка не продлилась — напишите в поддержку")
    return {"ok": True, "days": int(res)}


class _Sent:
    def __init__(s, box, i): s.box, s.i = box, i
    async def edit_text(s, text, **k): s.box[s.i] = text; return s
    edit_caption = edit_text
    def __getattr__(s, n):
        async def noop(*a, **k): return s
        return noop


class _Msg:
    """Подмена types.Message: хендлеры бота пишут ответы сюда, мини-приложение показывает их."""
    def __init__(s, text, tg):
        u = type("U", (), {"id": tg["id"], "username": tg.get("username"), "first_name": tg.get("first_name", ""),
                           "full_name": tg.get("first_name", ""), "is_bot": False})()
        s.text, s.from_user, s.bot, s.box, s.message_id = text, u, C["bot"], [], 0
        s.chat = type("Ch", (), {"id": tg["id"], "type": "private"})()
    async def answer(s, text="", **k): s.box.append(text); return _Sent(s.box, len(s.box) - 1)
    reply = answer
    def __getattr__(s, n):
        async def noop(*a, **k): return _Sent(s.box, 0) if s.box else None
        return noop


async def m_cmd(uid, tg, b):
    name, args = str(b.get("cmd") or ""), re.sub(r"[\r\n]+", " ", str(b.get("args") or "")).strip()[:300]
    fn = C["commands"].get(name)
    if not fn or role_of(uid) not in CMD_ROLES.get(name, ()): return err("Команда недоступна")
    msg, prm, kw = _Msg(f"/{name} {args}".strip(), tg), inspect.signature(fn).parameters, {}
    if "command" in prm: kw["command"] = C["CommandObject"](prefix="/", command=name, args=args or None)
    if "bot" in prm: kw["bot"] = C["bot"]
    logging.info(f"[MINIAPP CMD] {uid}: /{name} {args}")
    if name in ("update_servers", "start_promo"):
        asyncio.create_task(fn(msg, **kw)); return {"ok": True, "out": ["⏳ Запущено в фоне. Результат придёт в чат с ботом (рассылка/обновление идут без ограничения по времени)."]}
    try: await asyncio.wait_for(fn(msg, **kw), timeout=90)
    except asyncio.TimeoutError: msg.box.append("⏳ Команда выполняется дольше обычного — проверьте результат позже.")
    except Exception as e:
        logging.error(f"[MINIAPP CMD] {name}: {e}", exc_info=True); return err("Команда завершилась ошибкой — подробности в логах бота")
    return {"ok": True, "out": msg.box or ["Готово"]}


async def m_tables(uid, tg, b):
    if not staff(uid, "creator"): return err("Нет доступа")
    return {"ok": True, "tables": [{"name": n, "title": docs_of(n)["title"],
            "count": (q(f'SELECT COUNT(*) c FROM "{n}"', one=True) or {"c": 0})["c"]} for n in tables()]}


async def m_table(uid, tg, b):
    if not staff(uid, "creator"): return err("Нет доступа")
    n = str(b.get("name") or "")
    if n not in tables(): return err("Таблица не найдена")
    page = max(0, int(b.get("page") or 0))
    rows = clean(q(f'SELECT * FROM "{n}" ORDER BY rowid DESC LIMIT 30 OFFSET ?', (page * 30,)))
    return {"ok": True, "rows": rows, "docs": docs_of(n)}


async def m_ufull(uid, tg, b):
    """Полная карточка пользователя: строки из ВСЕХ таблиц, где он встречается."""
    if not staff(uid, "creator", "admin"): return err("Нет доступа")
    tid = int(b.get("id") or 0)
    if not q("SELECT 1 FROM users WHERE user_id=?", (tid,), one=True): return err("Пользователь не найден")
    out = []
    for n in tables():
        cols = [c["name"] for c in q(f'PRAGMA table_info("{n}")')]
        used = [c for c in USER_COLS if c in cols]
        if not used: continue
        rows = clean(q(f'SELECT * FROM "{n}" WHERE ' + " OR ".join(f'"{c}"=?' for c in used) + " ORDER BY rowid DESC LIMIT 15", (tid,) * len(used)))
        if rows: out.append({"table": n, "docs": docs_of(n), "rows": rows})
    return {"ok": True, "id": tid, "role": role_of(tid), "blocks": out}


async def m_overview2(uid, tg, b):
    if not staff(uid, "creator"): return err("Нет доступа")
    now = int(time.time()); day = {}
    for r in q("SELECT ts, paid_rub FROM purchases WHERE ts>?", (now - 14 * 86400,)):
        k = time.strftime("%d.%m", time.gmtime((r["ts"] or 0) + 3 * 3600)); day[k] = day.get(k, 0) + (r["paid_rub"] or 0)
    days = [time.strftime("%d.%m", time.gmtime(now + 3 * 3600 - i * 86400)) for i in range(13, -1, -1)]
    s = q("SELECT COUNT(*) c, COALESCE(SUM(paid_rub),0) s FROM purchases WHERE ts>?", (now - 30 * 86400,), one=True) or {"c": 0, "s": 0}
    roles = q("SELECT COALESCE(role,'user') role, COUNT(*) c FROM users GROUP BY role ORDER BY c DESC")
    pend = (q("SELECT COUNT(*) c FROM partner_withdrawals WHERE status='pending'", one=True) or {"c": 0})["c"]
    return {"ok": True, "rev30": s["s"], "purchases30": s["c"], "chart": [{"d": d, "v": day.get(d, 0)} for d in days], "roles": roles, "pending": pend}


async def m_withdraw(uid, tg, b):
    if role_of(uid) == "user": return err("Недоступно")
    method, cred = b.get("method"), str(b.get("credentials") or "").strip()[:200]
    if method not in ("card", "cryptobot") or len(cred) < 4: return err("Укажите способ и реквизиты")
    bal = C["get_partner_profile"](uid)[0] or 0
    if bal < 2500: return err("Минимальная сумма вывода — 2500 ₽")
    if q("SELECT 1 FROM partner_withdrawals WHERE partner_id=? AND status='pending'", (uid,), one=True): return err("У вас уже есть заявка на рассмотрении")
    rid = C["create_withdrawal_request"](uid, bal, method, cred)
    if not rid: return err("Не удалось создать заявку")
    KB, KBt = C["InlineKeyboardMarkup"], C["InlineKeyboardButton"]
    try:
        await C["bot"].send_message(C["ADMIN_ID"],
            f"💰 <b>ЗАЯВКА НА ВЫВОД СРЕДСТВ</b>\n\n👤 Партнёр: ID <code>{uid}</code> (@{tg.get('username') or 'нет'})\n💵 Сумма: <b>{bal} руб.</b>\n"
            f"📊 Метод: <b>{'Карта' if method == 'card' else 'CryptoBot'}</b>\n📌 Реквизиты: <code>{cred}</code>", parse_mode="HTML",
            reply_markup=KB(inline_keyboard=[[KBt(text="✅ Выплачено (Списать баланс)", callback_data=f"p_pay_{rid}"),
                                              KBt(text="❌ Отклонить", callback_data=f"p_reject_{rid}")]]))
    except Exception as e: logging.error(f"[MINIAPP] уведомление о выводе: {e}")
    return {"ok": True}


async def m_withdrawals(uid, tg, b):
    if not staff(uid, "creator"): return err("Нет доступа")
    return {"ok": True, "rows": q("SELECT id, partner_id, amount, method, credentials, status, created_at FROM partner_withdrawals ORDER BY (status='pending') DESC, id DESC LIMIT 30")}


async def m_withdraw_decide(uid, tg, b):
    if not staff(uid, "creator"): return err("Нет доступа")
    rid, act = int(b.get("id") or 0), b.get("action")
    row = q("SELECT partner_id, amount, status FROM partner_withdrawals WHERE id=?", (rid,), one=True)
    if not row or row["status"] != "pending": return err("Заявка не найдена или уже обработана")
    if act == "pay":
        if not C["confirm_withdrawal_db"](rid): return err("Не удалось списать баланс")
        text = f"💸 <b>Выплата успешно произведена!</b>\n\nСумма <b>{row['amount']} руб.</b> отправлена на ваши реквизиты."
    else:
        ex("UPDATE partner_withdrawals SET status='rejected' WHERE id=?", (rid,))
        text = f"⚠️ Ваша заявка на вывод <b>{row['amount']} руб.</b> отклонена. Обратитесь в поддержку."
    try: await C["bot"].send_message(row["partner_id"], text, parse_mode="HTML")
    except Exception: pass
    return {"ok": True}


METHODS = {"promo": m_promo, "cmd": m_cmd, "tables": m_tables, "table": m_table, "ufull": m_ufull, "overview2": m_overview2,
           "withdraw": m_withdraw, "withdrawals": m_withdrawals, "withdraw_decide": m_withdraw_decide}


async def handle(request: web.Request):
    fn, tg = METHODS.get(request.match_info["method"]), verify(request.headers.get("X-Init-Data", ""))
    if not fn or not tg: return web.json_response(err("Откройте приложение из Telegram"), status=401)
    try:
        body = await request.json() if request.can_read_body else {}
        return web.json_response(await fn(int(tg["id"]), tg, body if isinstance(body, dict) else {}))
    except Exception as e:
        logging.error(f"[MINIAPP] {request.match_info['method']}: {e}", exc_info=True)
        return web.json_response(err("Внутренняя ошибка, попробуйте позже"))


async def start_server():
    app = web.Application(client_max_size=64 * 1024)
    app.router.add_post("/miniapp/api/{method}", handle)
    async def ping(r): return web.json_response({"ok": True})
    app.router.add_get("/miniapp/api", ping)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.getenv("MINIAPP_PORT") or 8081)
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logging.info(f"[MINIAPP] API слушает порт {port}")
    return runner