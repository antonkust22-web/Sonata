"""
premium_emoji.py — премиум-эмодзи Sonata VPN (набор https://t.me/addemoji/Sonata_VPN)

Как это работает
  • При старте бот сам читает набор через getStickerSet и берёт оттуда id эмодзи
    (вручную id копировать не нужно).
  • Перед отправкой каждого сообщения модуль по ТАБЛИЦАМ ПРАВИЛ НИЖЕ заменяет
    нужные обычные эмодзи на премиум: в тексте — <tg-emoji>, на кнопках — иконку
    (icon_custom_emoji_id). Правила точные: эмодзи + слова рядом, ничего «на авось».
  • Если Telegram отклоняет сообщение с премиум-эмодзи, то оно тут же уходит
    повторно с обычными. После 3 таких случаев модуль выключается и пишет админу.

Подключение (в боте):
    import premium_emoji
    ...
    async def main():
        ...
        init_db()
        await premium_emoji.setup(bot, dp, ADMIN_ID)   # <- одна строка

Команды для админа: /emoji_map  /emoji_test  /emoji_reload  /emoji_off  /emoji_on
"""
import json
import logging
import os
import re

try:
    from aiogram.client.session.middlewares.base import BaseRequestMiddleware
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.filters import Command
except ImportError:                       # для тестов вне бота
    BaseRequestMiddleware = object
    TelegramBadRequest = Exception
    Command = None

PACK_NAME = "Sonata_VPN"
CACHE_PATH = "/data/premium_emoji.json"   # запасной кэш id, если набор не прочитался при старте
ENABLED = True                            # главный рубильник
MAX_FAILS = 3                             # столько отказов Telegram — и модуль сам отключается

# Если авто-определение ошиблось, можно вписать id вручную: {"handshake": "5123456789012345678"}
MANUAL = {}

# ------------------------------------------------------------------------------------------
# 1. КАКОЙ ФАЙЛ ПАКА ЧЕМ БЫЛ ОБЗВАН: ключ -> эмодзи, к которому он привязан в наборе
# ------------------------------------------------------------------------------------------
SPEC = {
    "wave": ["👋"], "whitelist": ["🖥"], "book": ["📖"], "connect": ["📲"], "user": ["👤"],
    "card": ["💳"], "promo": ["🎟"], "clock": ["⏰"], "bell_off": ["🔕"], "phone": ["📱"],
    "link": ["🔗"], "sparkle": ["✨"], "back": ["⬅️"], "cart": ["🛒"], "rocket": ["🚀"],
    "check": ["✅"], "bolt": ["⚡"], "qr": ["🖼"], "refresh": ["🔄"], "calendar": ["📅"],
    "clip": ["📋"], "globe": ["🌍"], "expired": ["❌", "🔴", "🛑"],
    # "friends" (👥) и "handshake" (🤝) разбираются отдельно в pick_ids()
}


def _norm(ch):
    return (ch or "").replace("\ufe0f", "").strip()


def pick_ids(rows):
    """rows: [(эмодзи_привязки, custom_emoji_id), ...] в порядке набора -> {ключ: id}"""
    by = {}
    for ch, cid in rows:
        by.setdefault(_norm(ch), []).append(cid)
    out = {}
    for key, chars in SPEC.items():
        for ch in chars:
            if by.get(ch):
                out[key] = by[ch][0]
                break
    handshakes = by.get("🤝", [])
    if handshakes:
        out["handshake"] = handshakes[-1]               # рукопожатие загружали последним
    if by.get("👥"):
        out["friends"] = by["👥"][0]
    elif len(handshakes) >= 2:
        out["friends"] = handshakes[0]                  # «два человека» мог быть привязан к 🤝
    out.update({k: v for k, v in MANUAL.items() if v})
    return out


# ------------------------------------------------------------------------------------------
# 2. ПРАВИЛА ЗАМЕНЫ
# ------------------------------------------------------------------------------------------
def E(ch):
    """эмодзи + необязательный селектор вариации"""
    return re.escape(ch) + "\ufe0f?"


# ТЕКСТ (только HTML-сообщения): эмодзи заменяется, если сразу за ним идут эти слова
_TEXT = [
    # главное меню / приветствие
    (E("👋") + r"(?=\s*Привет, добро пожаловать)", "wave"),
    (E("🖥") + r"(?=\s*У нас доступны Белые Списки)", "whitelist"),
    (E("📖") + r"(?=\s*Выберите действие)", "book"),
    # личный кабинет
    (E("👤") + r"(?=\s*Личный кабинет)", "user"),
    (r"(?<=</b> )" + E("👤") + r"(?=Пользователь\n)", "user"),
    (E("🤝") + r"(?=Партнер\n)", "handshake"),
    (E("🤝") + r"(?=\s*<b>(?:Партнерская программа|Новый реферал|Позовите друга))", "handshake"),
    (E("🔗") + r"(?=\s*Ссылка)", "link"),
    (E("👥") + r"(?=\s*Приглашено друзей)", "friends"),
    (E("✨") + r"(?=\s*Ваша подписка активна)", "sparkle"),
    (E("🔴") + r"(?=\s*Не активна)", "expired"),
    (E("📱") + r"(?=\s*(?:<b>Устройства:|<b>Управление устройствами|<b>Покупка дополнительных слотов|"
               r"<b>Все слоты|Устройство:|Доступный лимит устройств|Ваш лимит))", "phone"),
    # магазин и тарифы
    (E("💳") + r"(?=\s*<b>(?:Магазин Sonata VPN|Выбор тарифа))", "card"),
    (E("👤") + r"(?=\s*<b>Ваш ID:)", "user"),
    (E("🎟") + r"(?=\s*<b>Активация промокода)", "promo"),
    # подключение
    (E("🚀") + r"(?=\s*<b>РЕЖИМ ОТЛАДКИ)", "rocket"),
    (E("📅") + r"(?=\s*(?:Срок действия|Подписка продлена до|Новая дата окончания))", "calendar"),
    (E("✅") + r"(?=[^\n]*<b>Успешно подключен</b>)", "check"),
    (E("🖼") + r"(?=\s*<b>Ваш QR-код)", "qr"),
    (E("📋") + r"(?=\s*Информация об устройстве)", "clip"),
    # уведомления
    (E("⏰") + r"(?=\s*<b>Скидка)", "clock"),
    (E("🛑") + r"(?=\s*<b>Срок подписки истёк)", "expired"),
]
TEXT_RULES = [(re.compile(rx), key) for rx, key in _TEXT]

# КНОПКИ: (эмодзи, текст после него, ключ). Эмодзи уходит из текста, вместо него иконка.
_BTN = [
    ("📲", r"Подключиться", "connect"),
    ("👤", r"Личный кабинет|Пригласить Клиента", "user"),
    ("💳", r".+", "card"),
    ("🎟", r"Активировать промокод", "promo"),
    ("📖", r"Информация и поддержка|Инструкция", "book"),
    ("🛒", r"Купить подписку", "cart"),
    ("📱", r"Расширить лимит устройств|Докупить устройства", "phone"),
    ("📋", r"Мои устройства", "clip"),
    ("⚡", r"Импортировать.+", "bolt"),
    ("🖼", r"Получить QR-код", "qr"),
    ("🔄", r"Выбрать другое устройство|Я подписался.*", "refresh"),
    ("🔕", r"Отключить акции", "bell_off"),
    ("🤝", r"Пригласить Партнера", "handshake"),
    ("🚀", r"Годовой.+", "rocket"),
    ("⬅", r"Назад.*|Изменить ОС", "back"),
]
BTN_RULES = [(re.compile("^" + E(ch) + r"\s*(" + rest + ")$"), key) for ch, rest, key in _BTN]

# ------------------------------------------------------------------------------------------
# 3. СОСТОЯНИЕ
# ------------------------------------------------------------------------------------------
IDS = {}          # ключ -> custom_emoji_id
ROWS = []         # [(индекс, эмодзи привязки, id)] — для /emoji_map
_fails = 0
_ADMIN = None


def decorate_text(s):
    if not isinstance(s, str) or not IDS:
        return s
    for rx, key in TEXT_RULES:
        cid = IDS.get(key)
        if cid:
            s = rx.sub(lambda m, cid=cid: f'<tg-emoji emoji-id="{cid}">{m.group(0)}</tg-emoji>', s)
    return s


def decorate_button_text(text):
    """(новый_текст, id) или None, если у кнопки нет премиум-замены"""
    for rx, key in BTN_RULES:
        cid = IDS.get(key)
        m = rx.match(text or "")
        if cid and m:
            return m.group(1), cid
    return None


def _set(obj, attr, val):
    try:
        setattr(obj, attr, val)
    except Exception:
        object.__setattr__(obj, attr, val)


def decorate_request(method):
    """Подменяет text/caption/media/reply_markup у запроса. Возвращает {поле: оригинал} или {}."""
    saved = {}
    pm = getattr(method, "parse_mode", None)
    if pm == "HTML":
        for attr in ("text", "caption"):
            v = getattr(method, attr, None)
            nv = decorate_text(v)
            if nv != v:
                saved[attr] = v
                _set(method, attr, nv)
    media = getattr(method, "media", None)
    if media is not None and getattr(media, "parse_mode", None) == "HTML":
        v = getattr(media, "caption", None)
        nv = decorate_text(v)
        if nv != v:
            saved["media"] = media
            _set(method, "media", media.model_copy(update={"caption": nv}))
    rm = getattr(method, "reply_markup", None)
    rows = getattr(rm, "inline_keyboard", None)
    if rows:
        new_rows, changed = [], False
        for row in rows:
            new_row = []
            for b in row:
                r = None if getattr(b, "icon_custom_emoji_id", None) else decorate_button_text(b.text)
                if r:
                    changed = True
                    new_row.append(b.model_copy(update={"text": r[0], "icon_custom_emoji_id": r[1]}))
                else:
                    new_row.append(b)
            new_rows.append(new_row)
        if changed:
            saved["reply_markup"] = rm
            _set(method, "reply_markup", rm.model_copy(update={"inline_keyboard": new_rows}))
    return saved


def restore_request(method, saved):
    for attr, val in saved.items():
        _set(method, attr, val)


class PremiumEmojiMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        global ENABLED, _fails
        if not (ENABLED and IDS):
            return await make_request(bot, method)
        saved = decorate_request(method)
        if not saved:
            return await make_request(bot, method)
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as first_err:
            restore_request(method, saved)
            res = await make_request(bot, method)      # без премиум-эмодзи; если и это упало — ошибка не про эмодзи
            _fails += 1
            logging.warning(f"[EMOJI] Telegram отклонил премиум-эмодзи ({_fails}/{MAX_FAILS}): {first_err}")
            if _fails >= MAX_FAILS:
                ENABLED = False
                await _notify(bot, "⚠️ Премиум-эмодзи автоматически отключены: Telegram несколько раз отклонил сообщения с ними.\n"
                                   f"Ответ: {first_err}\n\nПроверьте, что у владельца бота есть Telegram Premium "
                                   "(или у бота куплены доп. юзернеймы на Fragment). Потом: /emoji_on")
            return res


async def _notify(bot, text):
    if _ADMIN:
        try:
            await bot.send_message(_ADMIN, text)
        except Exception as e:
            logging.error(f"[EMOJI] Не удалось написать админу: {e}")


# ------------------------------------------------------------------------------------------
# 4. ЗАГРУЗКА НАБОРА И КОМАНДЫ
# ------------------------------------------------------------------------------------------
async def reload_pack(bot):
    """Читает набор, заполняет IDS. Возвращает число найденных ключей."""
    global IDS, ROWS
    try:
        st = await bot.get_sticker_set(PACK_NAME)
        rows = [(i, s.emoji or "", s.custom_emoji_id) for i, s in enumerate(st.stickers) if s.custom_emoji_id]
        ROWS = rows
        IDS = pick_ids([(ch, cid) for _, ch, cid in rows])
        try:
            os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({"ids": IDS, "rows": rows}, f, ensure_ascii=False)
        except Exception as e:
            logging.warning(f"[EMOJI] Кэш не записан: {e}")
    except Exception as e:
        logging.error(f"[EMOJI] Не удалось прочитать набор {PACK_NAME}: {e}")
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            IDS, ROWS = d.get("ids", {}), [tuple(r) for r in d.get("rows", [])]
            logging.info(f"[EMOJI] Взяты id из кэша: {len(IDS)} шт.")
        except Exception:
            IDS, ROWS = {}, []
    logging.info(f"[EMOJI] Набор {PACK_NAME}: стикеров {len(ROWS)}, привязано ключей {len(IDS)}")
    return len(IDS)


def _is_admin(message):
    return _ADMIN is not None and message.from_user and message.from_user.id == _ADMIN


async def _cmd_map(message):
    if not _is_admin(message):
        return
    if not ROWS:
        await message.answer("Набор не прочитан. Проверьте PACK_NAME и /emoji_reload.")
        return
    used = {}
    for k, v in IDS.items():
        used.setdefault(v, []).append(k)
    lines = [f"<b>Набор {PACK_NAME}</b>: {len(ROWS)} шт. | Статус: {'✅ включено' if ENABLED else '⏸ выключено'}\n"]
    for i, ch, cid in ROWS:
        lines.append(f"{i + 1:02d} {ch} → <b>{', '.join(used.get(cid, ['—']))}</b>")
    missing = [k for k in list(SPEC) + ["friends", "handshake"] if k not in IDS]
    if missing:
        lines.append("\nНе найдены (останутся обычные эмодзи): " + ", ".join(missing))
    await message.answer("\n".join(lines), parse_mode="HTML")


async def _cmd_reload(message):
    if _is_admin(message):
        n = await reload_pack(message.bot)
        await message.answer(f"Готово: привязано ключей {n}. Подробности: /emoji_map")


async def _cmd_test(message):
    if not _is_admin(message):
        return
    if not IDS:
        await message.answer("Нет id эмодзи — набор не прочитан.")
        return
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    cid = IDS.get("handshake") or next(iter(IDS.values()))
    try:
        await message.bot.send_message(
            message.chat.id,
            f'Тест: <tg-emoji emoji-id="{cid}">🤝</tg-emoji> текст с премиум-эмодзи.\nЕсли выше обычный значок, а не анимированный, то у владельца бота нет Telegram Premium.',
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Кнопка с иконкой", callback_data="emoji_test", icon_custom_emoji_id=cid)]]))
    except Exception as e:
        await message.answer(f"❌ Telegram отклонил тест:\n{e}")


async def _cmd_off(message):
    global ENABLED
    if _is_admin(message):
        ENABLED = False
        await message.answer("⏸ Премиум-эмодзи выключены до перезапуска. Включить: /emoji_on")


async def _cmd_on(message):
    global ENABLED, _fails
    if _is_admin(message):
        ENABLED, _fails = True, 0
        await message.answer("✅ Премиум-эмодзи включены.")


async def setup(bot, dp, admin_id):
    """Вызвать один раз при старте бота (после init_db())."""
    global _ADMIN
    _ADMIN = admin_id
    bot.session.middleware(PremiumEmojiMiddleware())
    await reload_pack(bot)
    if Command is not None and dp is not None:
        for name, fn in (("emoji_map", _cmd_map), ("emoji_reload", _cmd_reload), ("emoji_test", _cmd_test),
                         ("emoji_off", _cmd_off), ("emoji_on", _cmd_on)):
            dp.message.register(fn, Command(name))
