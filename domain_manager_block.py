"""
domain_manager_block.py — смена домена + кнопка «Перевыпустить ключ» для бота Sonata VPN.

ПОДКЛЮЧЕНИЕ (одна строка в main.py, В САМОМ КОНЦЕ, прямо перед `if __name__ == '__main__':`):

    import domain_manager_block

Модуль сам найдёт bot, dp и функции бота и подключится.
Если хочешь импортировать вверху файла — тогда добавь в main() рядом с остальными setup:

    domain_manager_block.setup(globals())

Как работает «подмена домена везде» (править ссылки в main.py не нужно):
  1. Исходящие сообщения бота (текст, подписи, URL-кнопки, кнопка Mini App) перехватываются
     request-мидлварью aiogram, и sn-go.ru заменяется на актуальный домен.
  2. HTTP-запросы бота на sn-go.ru (синхронизация подписок, API устройств, Mini App sync)
     перенаправляются на актуальный домен; в тестовом режиме запись подписок дублируется на тестовый домен.
  3. QR-коды и ссылка для ТВ (Happ) тоже получают новый домен.

Режимы:
  test — новый домен видит ТОЛЬКО Создатель (ADMIN_ID), кнопка «Перевыпустить ключ (тест)» тоже только у него.
  live — новый домен у всех, кнопка видна всем.
Пока домен не задан командой /domain set — всё работает как раньше, кнопки нет.
"""
import asyncio
import base64
import contextvars
import json
import logging
import re
import sqlite3
import sys
import time

import aiohttp
from aiogram import BaseMiddleware, F, Router, types
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, WebAppInfo

BASE_DOMAIN = "sn-go.ru"      # домен, прописанный в коде бота (в коде его менять не надо)
DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")

_DM = {"live": "", "test": ""}
_G: dict = {}
_READY = False
_LOCK = asyncio.Lock()
_REISSUE_LAST: dict = {}
_CUR = contextvars.ContextVar("dm_uid", default=None)    # пользователь, чьё обновление сейчас обрабатывается
_RAW = contextvars.ContextVar("dm_raw", default=False)   # в /domain не подменяем тексты (там нужно видеть реальные домены)
router = Router(name="domain_manager")


def _g(name):
    return _G[name]


# ======================================================================
# Состояние (хранится в БД бота, переживает перезапуск)
# ======================================================================
def _conn():
    conn = sqlite3.connect(_g("DB_PATH"), timeout=30.0)
    conn.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def _load():
    try:
        conn = _conn()
        try:
            for k, v in conn.execute("SELECT key, value FROM app_settings WHERE key IN ('live_domain','test_domain')").fetchall():
                _DM[k.split("_")[0]] = v or ""
        finally:
            conn.close()
    except Exception as e:
        logging.error(f"[DOMAIN] не удалось прочитать настройки: {e}")


def _save():
    conn = _conn()
    try:
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('live_domain', ?)", (_DM["live"],))
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES ('test_domain', ?)", (_DM["test"],))
        conn.commit()
    finally:
        conn.close()


# ======================================================================
# Публичные помощники (можно вызывать и из main.py: domain_manager_block.site(...))
# ======================================================================
def primary_domain() -> str:
    return _DM["live"] or BASE_DOMAIN


def site_domain(user_id=None) -> str:
    uid = user_id if user_id is not None else _CUR.get()
    if _DM["test"] and uid == _G.get("ADMIN_ID"):
        return _DM["test"]
    return primary_domain()


def site(path: str = "", user_id=None) -> str:
    return f"https://{site_domain(user_id)}{path}"


def U(text, user_id=None):
    if not isinstance(text, str) or BASE_DOMAIN not in text:
        return text
    return text.replace(BASE_DOMAIN, site_domain(user_id))


def api_url() -> str:
    return f"https://{primary_domain()}/index.php"


def reissue_available(user_id=None) -> bool:
    uid = user_id if user_id is not None else _CUR.get()
    return bool(_DM["live"] or (_DM["test"] and uid == _G.get("ADMIN_ID")))


# ======================================================================
# 1) Перехват исходящих сообщений бота (aiogram request middleware)
# ======================================================================
def _rewrite_kb(kb: InlineKeyboardMarkup, uid):
    eff = uid if uid is not None else _CUR.get()
    rows, changed, is_final = [], False, False
    for row in kb.inline_keyboard:
        new_row = []
        for b in row:
            if b.callback_data and b.callback_data.startswith("showqr_"):
                is_final = True                       # финальный экран «Подключиться»
            if b.url and BASE_DOMAIN in b.url:
                b = b.model_copy(update={"url": _swap(b.url, uid)})
                changed = True
            new_row.append(b)
        rows.append(new_row)
    if is_final and reissue_available(eff) and not any(b.callback_data == "reissue_key" for r in rows for b in r):
        label = "🔑 Перевыпустить ключ (тест)" if (_DM["test"] and eff == _G.get("ADMIN_ID")) else "🔑 Перевыпустить ключ"
        rows.insert(min(2, len(rows)), [InlineKeyboardButton(text=label, callback_data="reissue_key")])
        changed = True
    return InlineKeyboardMarkup(inline_keyboard=rows) if changed else kb


def _swap(s, uid):
    if not isinstance(s, str) or BASE_DOMAIN not in s:
        return s
    return s.replace(BASE_DOMAIN, site_domain(uid))


def _rewrite_method(method):
    uid = getattr(method, "chat_id", None)
    uid = uid if isinstance(uid, int) else None

    if not _RAW.get():
        for fld in ("text", "caption"):
            v = getattr(method, fld, None)
            if isinstance(v, str) and BASE_DOMAIN in v:
                setattr(method, fld, _swap(v, uid))
        media = getattr(method, "media", None)
        cap = getattr(media, "caption", None) if media is not None and not isinstance(media, list) else None
        if isinstance(cap, str) and BASE_DOMAIN in cap:
            method.media = media.model_copy(update={"caption": _swap(cap, uid)})
        mb = getattr(method, "menu_button", None)
        wa = getattr(mb, "web_app", None) if mb is not None else None
        if wa is not None and BASE_DOMAIN in (wa.url or ""):
            method.menu_button = mb.model_copy(update={"web_app": wa.model_copy(update={"url": _swap(wa.url, uid)})})

    kb = getattr(method, "reply_markup", None)
    if isinstance(kb, InlineKeyboardMarkup):
        method.reply_markup = _rewrite_kb(kb, uid)


class _RewriteRequests(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        try:
            _rewrite_method(method)
        except Exception as e:
            logging.warning(f"[DOMAIN] не удалось переписать {type(method).__name__}: {e}")
        return await make_request(bot, method)


class _UserContext(BaseMiddleware):
    """Запоминает, чей апдейт обрабатывается (нужно для тестового режима: QR, ТВ и т.п.)."""
    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        token = _CUR.set(u.id if u else None)
        try:
            return await handler(event, data)
        finally:
            _CUR.reset(token)


# ======================================================================
# 2) Перенаправление HTTP-запросов бота (aiohttp) и QR
# ======================================================================
async def _mirror(method, url, kw):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.request(method, url, **kw) as r:
                await r.read()
    except Exception as e:
        logging.debug(f"[DOMAIN] зеркало {url}: {e}")


def _patch_aiohttp():
    orig = aiohttp.ClientSession._request
    marker = f"://{BASE_DOMAIN}"

    async def patched(self, method, str_or_url, **kw):
        try:
            url = str(str_or_url)
            if marker in url:
                if "update_sub=1" in url and _DM["test"] and str(method).upper() == "POST":
                    asyncio.create_task(_mirror(method, url.replace(marker, f"://{_DM['test']}", 1), dict(kw)))
                if primary_domain() != BASE_DOMAIN:
                    str_or_url = url.replace(marker, f"://{primary_domain()}", 1)
            elif "check.happ.su/sendtv" in url and isinstance(kw.get("json"), dict) and kw["json"].get("data"):
                decoded = base64.b64decode(kw["json"]["data"]).decode("utf-8")
                if BASE_DOMAIN in decoded:
                    kw["json"] = {**kw["json"], "data": base64.b64encode(_swap(decoded, None).encode("utf-8")).decode("utf-8")}
        except Exception as e:
            logging.warning(f"[DOMAIN] aiohttp-патч: {e}")
        return await orig(self, method, str_or_url, **kw)

    aiohttp.ClientSession._request = patched


def _patch_qr():
    try:
        import qrcode
        orig = qrcode.QRCode.add_data

        def add_data(self, data, optimize=20):
            return orig(self, _swap(data, None) if isinstance(data, str) else data, optimize)

        qrcode.QRCode.add_data = add_data
    except Exception as e:
        logging.warning(f"[DOMAIN] QR-патч не применён: {e}")


# ======================================================================
# 3) Перенос пользователей на домен и проверка домена
# ======================================================================
async def dm_push_user(user_id: int, domain: str) -> bool:
    """Кладёт подписку пользователя (конфиг, срок, ЛИМИТ УСТРОЙСТВ) на указанный домен."""
    row = _g("get_user_from_db")(user_id)
    if not row or not row[3]:
        return False
    try:
        expiry = int(row[4] or 0)
    except (TypeError, ValueError):
        expiry = 0
    limit = row[10] if (len(row) > 10 and row[10]) else _g("DEFAULT_DEVICE_LIMIT")
    if 0 < expiry <= int(time.time()) and not _g("_is_limit_exempt")(user_id, row[5]):
        limit = _g("DEFAULT_DEVICE_LIMIT")                 # истёкшим — стандартный лимит, как в device_limit_watchdog
    content = "" if expiry <= int(time.time()) else base64.b64encode((row[2] or "").strip().encode("utf-8")).decode("utf-8")
    payload = {"token": str(row[3]), "content": content, "expiry": str(expiry),
               "device_limit": str(int(limit)), "user_id": str(user_id)}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"https://{domain}/index.php?update_sub=1", data=payload,
                              timeout=aiohttp.ClientTimeout(total=8)) as r:
                await r.read()
                return r.status == 200
    except Exception as e:
        logging.error(f"[DOMAIN] push {user_id} -> {domain}: {e}")
        return False


async def dm_check(domain: str):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://{domain}/index.php?secret={_g('SECRET_KEY')}&get_user_by_sub=eprobe0000000000",
                             timeout=aiohttp.ClientTimeout(total=8)) as r:
                txt = await r.text()
        try:
            json.loads(txt)
            return True, "API отвечает"
        except ValueError:
            return False, "сайт открылся, но ответ не JSON — проверь, что index.php перенесён и SECRET_KEY совпадает"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def dm_sync_all(domain: str, status=None, menu: bool = False):
    conn = sqlite3.connect(_g("DB_PATH"), timeout=30.0)
    try:
        ids = [r[0] for r in conn.execute("SELECT user_id FROM users WHERE github_raw_url IS NOT NULL AND github_raw_url != ''").fetchall()]
    finally:
        conn.close()
    bot = _g("bot")
    ok, failed, last = 0, [], 0.0
    for i, uid in enumerate(ids, 1):
        good = False
        try:
            good = await dm_push_user(uid, domain)
        except Exception as e:
            logging.error(f"[DOMAIN] sync {uid}: {e}")
        if good:
            ok += 1
        else:
            failed.append(uid)
        if menu:
            try:
                await bot.set_chat_menu_button(chat_id=uid, menu_button=MenuButtonWebApp(
                    text="Open", web_app=WebAppInfo(url=f"https://{domain}/miniapp")))
            except Exception:
                pass
        if status and time.time() - last > 4:
            last = time.time()
            try:
                await status.edit_text(f"🔄 Перенос пользователей: {i} / {len(ids)}\n✅ {ok}  ❌ {len(failed)}")
            except Exception:
                pass
        await asyncio.sleep(0.05)
    return ok, failed, len(ids)


# ======================================================================
# 4) Команда /domain (только Создатель)
# ======================================================================
def _status_text() -> str:
    return ("🌐 <b>Домен Sonata VPN</b>\n\n"
            f"Основной: <code>{primary_domain()}</code>" + (" (из кода)" if not _DM["live"] else "") + "\n"
            f"Тестовый (видите только вы): <code>{_DM['test'] or '—'}</code>\n\n"
            "<b>Команды:</b>\n"
            "<code>/domain set новый.ру</code> — включить тест на новом домене\n"
            "<code>/domain sync</code> — заранее перенести всех пользователей на тестовый домен\n"
            "<code>/domain live</code> — переключить на новый домен ВСЕХ (с подтверждением)\n"
            "<code>/domain off</code> — отменить тест\n"
            "<code>/domain reset</code> — аварийно вернуть домен из кода")


@router.message(Command("domain"))
async def cmd_domain(message: types.Message, command: CommandObject):
    if message.from_user.id != _g("ADMIN_ID"):
        return
    _RAW.set(True)
    args = (command.args or "").split()
    sub = args[0].lower() if args else ""

    if sub == "set":
        if len(args) < 2:
            await message.answer("Формат: <code>/domain set новый-домен.ру</code>", parse_mode="HTML")
            return
        dom = args[1].lower().replace("https://", "").replace("http://", "").strip("/").split("/")[0]
        if not DOMAIN_RE.match(dom) or dom in (BASE_DOMAIN, primary_domain()):
            await message.answer("❌ Некорректный домен или он уже основной.")
            return
        ok, info = await dm_check(dom)
        if not ok:
            await message.answer(f"❌ Домен <code>{dom}</code> не принят: {info}", parse_mode="HTML")
            return
        _DM["test"] = dom
        _save()
        pushed = await dm_push_user(message.from_user.id, dom)
        await message.answer(
            f"✅ <b>Тест включён:</b> <code>{dom}</code> ({info})\n"
            f"Ваша подписка на нём: {'создана' if pushed else '⚠️ не создалась (смотрите лог)'}\n\n"
            "Все ссылки и кнопка «🔑 Перевыпустить ключ (тест)» теперь видны <b>только вам</b>. "
            "Откройте «Подключиться» и проверьте. Остальные пока на старом домене.\n"
            "Когда всё ок: <code>/domain sync</code>, затем <code>/domain live</code>.", parse_mode="HTML")
        return

    if sub == "off":
        _DM["test"] = ""
        _save()
        await message.answer("↩️ Тестовый домен отключён.")
        return

    if sub == "reset":
        _DM["live"], _DM["test"] = "", ""
        _save()
        await message.answer(f"↩️ Основной домен снова <code>{BASE_DOMAIN}</code> (из кода).", parse_mode="HTML")
        return

    if sub == "sync":
        if not _DM["test"]:
            await message.answer("Сначала задайте тестовый домен: <code>/domain set ...</code>", parse_mode="HTML")
            return
        if _LOCK.locked():
            await message.answer("⏳ Перенос уже идёт.")
            return
        async with _LOCK:
            st = await message.answer("🔄 Перенос пользователей: 0")
            ok, failed, total = await dm_sync_all(_DM["test"], st)
            await st.edit_text(f"✅ Готово: <b>{ok}</b> из {total}, ошибок: <b>{len(failed)}</b>", parse_mode="HTML")
        return

    if sub == "live":
        if not _DM["test"]:
            await message.answer("Сначала задайте тестовый домен: <code>/domain set ...</code>", parse_mode="HTML")
            return
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, переключить всех", callback_data="dm:live")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="dm:cancel")]])
        await message.answer(
            f"⚠️ <b>Переключить всех на <code>{_DM['test']}</code>?</b>\n\n"
            "Бот сначала перенесёт всех пользователей (срок, лимиты устройств), и только потом переключит ссылки. "
            "У всех появится кнопка «Перевыпустить ключ».", reply_markup=kb, parse_mode="HTML")
        return

    await message.answer(_status_text(), parse_mode="HTML")


@router.callback_query(F.data.startswith("dm:"))
async def cb_domain(callback: types.CallbackQuery):
    if callback.from_user.id != _g("ADMIN_ID"):
        await callback.answer("❌ Нет прав.", show_alert=True)
        return
    _RAW.set(True)
    if callback.data == "dm:cancel":
        await callback.answer()
        await callback.message.edit_text("Отменено.")
        return
    if not _DM["test"]:
        await callback.answer("Тестовый домен не задан.", show_alert=True)
        return
    if _LOCK.locked():
        await callback.answer("Уже выполняется.", show_alert=True)
        return
    await callback.answer("Запускаю…")
    async with _LOCK:
        dom = _DM["test"]
        await callback.message.edit_text("🔄 Перенос пользователей: 0")
        ok, failed, total = await dm_sync_all(dom, callback.message, menu=True)
        if total and len(failed) / total > 0.1:
            await callback.message.edit_text(
                f"🛑 Не переключаю: ошибок слишком много ({len(failed)} из {total}). Проверьте домен и повторите /domain live.")
            return
        _DM["live"], _DM["test"] = dom, ""
        _save()
        try:
            await _g("bot").set_chat_menu_button(menu_button=MenuButtonWebApp(text="Open", web_app=WebAppInfo(url=f"https://{dom}/miniapp")))
        except Exception as e:
            logging.warning(f"[DOMAIN] default menu button: {e}")
        await callback.message.edit_text(
            f"✅ <b>Основной домен: <code>{dom}</code></b>\nПеренесено: {ok} из {total}, ошибок: {len(failed)}.\n"
            "Ссылки везде обновились, у пользователей появилась кнопка «Перевыпустить ключ».", parse_mode="HTML")


# ======================================================================
# 5) Кнопка «Перевыпустить ключ»
# ======================================================================
@router.callback_query(F.data == "reissue_key")
async def reissue_key(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not reissue_available(user_id):
        await callback.answer("Функция пока недоступна.", show_alert=True)
        return
    if time.time() - _REISSUE_LAST.get(user_id, 0) < 20:
        await callback.answer("Подождите несколько секунд…")
        return
    _REISSUE_LAST[user_id] = time.time()
    await callback.answer("Перевыпускаю ключ…")

    dom = site_domain(user_id)
    if not await dm_push_user(user_id, dom):
        await callback.message.answer("⚠️ Не удалось перевыпустить ключ. Попробуйте позже или напишите в поддержку.")
        return

    row = _g("get_user_from_db")(user_id)
    import hashlib
    sub_id = row[3] if row and row[3] else "e" + hashlib.md5(str(user_id).encode()).hexdigest()[:15]
    await callback.message.answer(
        "🔑 <b>Ключ перевыпущен</b>\n\n"
        f"Новая ссылка подписки:\n<code>{site('/' + sub_id, user_id)}</code>\n\n"
        "<blockquote>Удалите старую подписку в приложении и добавьте новую кнопкой ниже. "
        "Сервера и срок подписки не изменились.</blockquote>", parse_mode="HTML")
    saved_os = row[8] if row and len(row) > 8 else None
    saved_app = row[9] if row and len(row) > 9 else None
    if saved_os and saved_app:
        await _g("process_final_screen")(callback, user_id, callback.from_user.username or "", row, saved_os, saved_app)


# ======================================================================
# Подключение
# ======================================================================
def setup(g: dict):
    """Подключает модуль к боту. Безопасно вызывать повторно."""
    global _READY
    if _READY:
        return
    _G.update(g)
    _READY = True
    _load()
    dp, bot = g["dp"], g["bot"]
    dp.update.outer_middleware(_UserContext())
    bot.session.middleware(_RewriteRequests())
    _patch_aiohttp()
    _patch_qr()
    dp.include_router(router)
    logging.info(f"[DOMAIN] модуль подключён. Основной: {primary_domain()}, тестовый: {_DM['test'] or '—'}")


def _autostart():
    m = sys.modules.get("__main__")
    needed = ("bot", "dp", "ADMIN_ID", "DB_PATH", "SECRET_KEY", "get_user_from_db", "process_final_screen",
              "DEFAULT_DEVICE_LIMIT", "_is_limit_exempt")
    if m is not None and all(hasattr(m, n) for n in needed):
        setup(vars(m))


_autostart()