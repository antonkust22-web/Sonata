# =====================================================================
# 📣 УЧЁТ РЕКЛАМНЫХ ССЫЛОК  (отдельный модуль ads_tracker.py)
#
# Подключение в основном файле бота (3 строки):
#   1) вверху, рядом с другими import:                 import ads_tracker
#   2) в cmd_start, сразу после строки
#          is_new_user = existing_user is None
#      добавить:
#          ads_tracker.track_start(user_id, command.args if command else None, is_new_user)
#   3) в main(), после trial_block.setup(globals()):   ads_tracker.setup(globals())
#
# Как пользоваться (только Создатель, ADMIN_ID):
#   /ad ads1            — создать ссылку «ads1» (или показать статистику, если уже есть)
#   /ad ads1 Канал Вася — то же + заметка, чтобы не забыть, где размещена реклама
#   /ads                — список всех ссылок с итогами
#   /adcost ads1 5000   — сколько вы заплатили за рекламу (посчитает цену клиента и окупаемость)
#   /addel ads1         — удалить ссылку вместе со статистикой
#
# Ссылка выглядит так: https://t.me/<бот>?start=ad_ads1
#
# Что считается:
#   • Переходы   — сколько раз нажали /start по ссылке (и сколько разных людей).
#   • Новые      — люди, которые раньше не были в боте. Источник закрепляется за первой ссылкой.
#   • Прошли проверку — новые, которые прошли капчу и попали в базу.
#   • Оплатили   — покупки подписки (таблица purchases) людей, пришедших как НОВЫЕ по этой ссылке.
#                  Покупка слотов устройств в учёт оплат не входит (как и в ретеншн-движке).
#   Старые пользователи, перешедшие по ссылке, попадают только в «переходы» — их источник не меняется.
# =====================================================================
import html as _html
import logging
import re
import sqlite3
import time

from aiogram import F, Router, types
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

router = Router()

_NEEDED = ["bot", "dp", "ADMIN_ID", "DB_PATH"]
_CODE_RX = re.compile(r"^[a-z0-9_-]{1,32}$")
_READY = False
_BOT_USERNAME = None


def setup(g: dict):
    """Вызвать один раз в main(): ads_tracker.setup(globals())"""
    missing = [n for n in _NEEDED if n not in g]
    if missing:
        raise RuntimeError(f"[ADS] В основном файле не найдено: {', '.join(missing)}")
    globals().update({n: g[n] for n in _NEEDED})
    _db().close()                      # создать таблицы сразу при старте
    g["dp"].include_router(router)
    logging.info("[ADS] Модуль учёта рекламных ссылок подключён")


# ---------------------------------------------------------------- БАЗА
def _db():
    global _READY
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    if not _READY:
        conn.execute('''CREATE TABLE IF NOT EXISTS ad_links (
            code TEXT PRIMARY KEY, note TEXT DEFAULT '', cost REAL DEFAULT 0, created_ts INTEGER)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS ad_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, user_id INTEGER, ts INTEGER, is_new INTEGER DEFAULT 0)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS ad_users (
            user_id INTEGER PRIMARY KEY, code TEXT, ts INTEGER)''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ad_clicks_code ON ad_clicks(code, ts)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_ad_users_code ON ad_users(code, ts)')
        conn.commit()
        _READY = True
    return conn


def track_start(user_id: int, args, is_new_user: bool):
    """Вызывается из cmd_start. Никогда не бросает исключений — /start не должен ломаться из-за учёта."""
    try:
        a = (args or "").strip()
        if not a.lower().startswith("ad_"):
            return
        code = a[3:].lower()
        if not _CODE_RX.match(code):
            return
        conn = _db()
        try:
            if not conn.execute("SELECT 1 FROM ad_links WHERE code=?", (code,)).fetchone():
                return                  # учитываем только созданные командой /ad ссылки
            now = int(time.time())
            conn.execute("INSERT INTO ad_clicks (code, user_id, ts, is_new) VALUES (?,?,?,?)",
                         (code, user_id, now, 1 if is_new_user else 0))
            if is_new_user:             # источник закрепляется за первой ссылкой
                conn.execute("INSERT OR IGNORE INTO ad_users (user_id, code, ts) VALUES (?,?,?)", (user_id, code, now))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logging.error(f"[ADS] Ошибка учёта перехода {user_id}: {e}", exc_info=True)


def get_stats(code: str, since: int = 0) -> dict:
    conn = _db()
    try:
        c = conn.cursor()
        clicks, uniq = c.execute("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM ad_clicks WHERE code=? AND ts>=?",
                                 (code, since)).fetchone()
        new = c.execute("SELECT COUNT(*) FROM ad_users WHERE code=? AND ts>=?", (code, since)).fetchone()[0]
        reg = c.execute("SELECT COUNT(*) FROM ad_users a JOIN users u ON u.user_id=a.user_id "
                        "WHERE a.code=? AND a.ts>=?", (code, since)).fetchone()[0]
        try:
            buyers, buys, rub = c.execute(
                "SELECT COUNT(DISTINCT p.user_id), COUNT(*), COALESCE(SUM(p.paid_rub),0) "
                "FROM ad_users a JOIN purchases p ON p.user_id=a.user_id AND p.ts>=a.ts "
                "WHERE a.code=? AND a.ts>=?", (code, since)).fetchone()
        except sqlite3.OperationalError:    # таблицы purchases ещё нет — покупок не было
            buyers, buys, rub = 0, 0, 0
        return {"clicks": clicks, "unique": uniq, "new": new, "reg": reg,
                "buyers": buyers, "buys": buys, "rub": int(rub or 0)}
    finally:
        conn.close()


def _get_link(code: str):
    conn = _db()
    try:
        r = conn.execute("SELECT code, note, cost, created_ts FROM ad_links WHERE code=?", (code,)).fetchone()
        return {"code": r[0], "note": r[1] or "", "cost": float(r[2] or 0), "created_ts": r[3]} if r else None
    finally:
        conn.close()


# ---------------------------------------------------------------- ВЫВОД
def _money(v) -> str:
    return f"{int(round(v)):,}".replace(",", " ")


def _pct(a, b) -> str:
    return f"{a * 100 / b:.1f}%" if b else "—"


async def _link_url(code: str) -> str:
    global _BOT_USERNAME
    if not _BOT_USERNAME:
        _BOT_USERNAME = (await bot.get_me()).username
    return f"https://t.me/{_BOT_USERNAME}?start=ad_{code}"


async def _stat_text(link: dict) -> str:
    code = link["code"]
    now = int(time.time())
    st, d1 = get_stats(code), get_stats(code, now - 86400)
    url = await _link_url(code)
    lines = [f"📊 <b>Реклама: {_html.escape(code)}</b>"]
    if link["note"]:
        lines.append(f"📝 {_html.escape(link['note'])}")
    lines += [
        f"🔗 <code>{url}</code>\n",
        f"👆 Переходов: <b>{st['clicks']}</b> (разных людей: {st['unique']})",
        f"🆕 Новых в боте: <b>{st['new']}</b>",
        f"✅ Прошли проверку: <b>{st['reg']}</b>",
        f"💳 Оплатили: <b>{st['buyers']}</b> чел. · покупок: {st['buys']} · <b>{_money(st['rub'])} ₽</b>",
        f"📈 Из новых в оплату: <b>{_pct(st['buyers'], st['new'])}</b>",
    ]
    if link["cost"] > 0:
        cost = link["cost"]
        lines.append(f"\n💰 Расход на рекламу: <b>{_money(cost)} ₽</b>")
        if st["new"]:
            lines.append(f"• цена нового пользователя: {_money(cost / st['new'])} ₽")
        if st["buyers"]:
            lines.append(f"• цена платящего клиента: {_money(cost / st['buyers'])} ₽")
        lines.append(f"• окупаемость: <b>{(st['rub'] - cost) * 100 / cost:+.0f}%</b> ({_money(st['rub'] - cost)} ₽)")
    lines.append(f"\n🕐 За последние 24 ч: переходов {d1['clicks']}, новых {d1['new']}, оплатили {d1['buyers']}")
    lines.append("<i>Оплаты считаются у новых пользователей, пришедших по этой ссылке.</i>")
    return "\n".join(lines)


def _link_kb(code: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"adst:{code}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adel:ask:{code}"),
    ]])


# ---------------------------------------------------------------- КОМАНДЫ
def _parse_code(raw: str):
    code = (raw or "").strip().lower()
    if code.startswith("ad_"):
        code = code[3:]
    return code if _CODE_RX.match(code) else None


@router.message(Command("ad"))
async def cmd_ad(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    parts = (command.args or "").split(maxsplit=1)
    if not parts:
        await message.answer(
            "📣 <b>Рекламные ссылки</b>\n\n"
            "<code>/ad ads1</code> — создать ссылку или посмотреть статистику\n"
            "<code>/ad ads1 Канал Вася</code> — с заметкой\n"
            "<code>/ads</code> — все ссылки\n"
            "<code>/adcost ads1 5000</code> — указать расход на рекламу\n"
            "<code>/addel ads1</code> — удалить ссылку\n\n"
            "Код: латинские буквы, цифры, <code>_</code> и <code>-</code>, до 32 символов.", parse_mode="HTML")
        return
    code = _parse_code(parts[0])
    if not code:
        await message.answer("❌ Код может содержать только латинские буквы, цифры, <code>_</code> и <code>-</code> (до 32 символов).",
                             parse_mode="HTML")
        return
    note = parts[1].strip()[:100] if len(parts) > 1 else ""
    conn = _db()
    try:
        exists = conn.execute("SELECT 1 FROM ad_links WHERE code=?", (code,)).fetchone()
        if not exists:
            conn.execute("INSERT INTO ad_links (code, note, cost, created_ts) VALUES (?,?,0,?)", (code, note, int(time.time())))
        elif note:
            conn.execute("UPDATE ad_links SET note=? WHERE code=?", (note, code))
        conn.commit()
    finally:
        conn.close()
    head = "" if exists else "✅ <b>Ссылка создана.</b> Ставьте её в рекламу:\n\n"
    await message.answer(head + await _stat_text(_get_link(code)), parse_mode="HTML",
                         reply_markup=_link_kb(code), disable_web_page_preview=True)


@router.message(Command("ads"))
async def cmd_ads(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = _db()
    try:
        rows = conn.execute("SELECT code, note FROM ad_links ORDER BY created_ts DESC LIMIT 30").fetchall()
    finally:
        conn.close()
    if not rows:
        await message.answer("Пока нет рекламных ссылок. Создайте: <code>/ad ads1</code>", parse_mode="HTML")
        return
    lines, tot = ["📣 <b>Рекламные ссылки</b>\n"], {"clicks": 0, "new": 0, "buyers": 0, "rub": 0}
    for code, note in rows:
        st = get_stats(code)
        for k in tot:
            tot[k] += st[k]
        tail = f" · {_html.escape(note)}" if note else ""
        lines.append(f"<code>{_html.escape(code)}</code>{tail}\n"
                     f"   👆 {st['clicks']} · 🆕 {st['new']} · 💳 {st['buyers']} · {_money(st['rub'])} ₽")
    lines.append(f"\n<b>Итого:</b> 👆 {tot['clicks']} · 🆕 {tot['new']} · 💳 {tot['buyers']} · {_money(tot['rub'])} ₽")
    lines.append("<i>Подробно по одной: /ad код</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("adcost"))
async def cmd_adcost(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    parts = (command.args or "").split()
    code = _parse_code(parts[0]) if parts else None
    try:
        cost = float(parts[1].replace(",", ".")) if len(parts) > 1 else None
    except ValueError:
        cost = None
    if not code or cost is None or cost < 0:
        await message.answer("Формат: <code>/adcost ads1 5000</code> (сумма в рублях)", parse_mode="HTML")
        return
    conn = _db()
    try:
        cur = conn.execute("UPDATE ad_links SET cost=? WHERE code=?", (cost, code))
        conn.commit()
        found = cur.rowcount > 0
    finally:
        conn.close()
    if not found:
        await message.answer(f"❌ Ссылки <code>{_html.escape(code)}</code> нет. Создайте: <code>/ad {_html.escape(code)}</code>", parse_mode="HTML")
        return
    await message.answer(await _stat_text(_get_link(code)), parse_mode="HTML",
                         reply_markup=_link_kb(code), disable_web_page_preview=True)


@router.message(Command("addel"))
async def cmd_addel(message: types.Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return
    code = _parse_code(command.args or "")
    if not code or not _get_link(code):
        await message.answer("Формат: <code>/addel ads1</code> — такой ссылки нет или код неверный.", parse_mode="HTML")
        return
    await _ask_delete(message, code)


async def _ask_delete(message: types.Message, code: str):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"adel:yes:{code}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="adel:no:-"),
    ]])
    await message.answer(f"Удалить ссылку <code>{_html.escape(code)}</code> вместе со всей статистикой? "
                         "Люди, пришедшие по ней, останутся в боте, но учёт оплат по этой ссылке пропадёт.",
                         parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("adst:"))
async def cb_stat(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав.", show_alert=True)
        return
    code = _parse_code(callback.data.split(":", 1)[1])
    link = _get_link(code) if code else None
    if not link:
        await callback.answer("Ссылка не найдена.", show_alert=True)
        return
    await callback.answer("Обновлено")
    try:
        await callback.message.edit_text(await _stat_text(link), parse_mode="HTML",
                                         reply_markup=_link_kb(code), disable_web_page_preview=True)
    except Exception:
        pass                              # «message is not modified» — данные не изменились


@router.callback_query(F.data.startswith("adel:"))
async def cb_delete(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Нет прав.", show_alert=True)
        return
    _, action, code = (callback.data.split(":", 2) + ["", ""])[:3]
    if action == "no":
        await callback.answer("Отменено")
        try:
            await callback.message.delete()
        except Exception:
            pass
        return
    code = _parse_code(code)
    if not code or not _get_link(code):
        await callback.answer("Ссылка уже удалена.", show_alert=True)
        return
    if action == "ask":
        await callback.answer()
        await _ask_delete(callback.message, code)
        return
    if action == "yes":
        conn = _db()
        try:
            conn.execute("DELETE FROM ad_clicks WHERE code=?", (code,))
            conn.execute("DELETE FROM ad_users WHERE code=?", (code,))
            conn.execute("DELETE FROM ad_links WHERE code=?", (code,))
            conn.commit()
        finally:
            conn.close()
        await callback.answer("Удалено")
        try:
            await callback.message.edit_text(f"🗑 Ссылка <code>{_html.escape(code)}</code> удалена.", parse_mode="HTML")
        except Exception:
            pass