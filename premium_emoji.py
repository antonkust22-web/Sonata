"""
premium_emoji.py — премиум-эмодзи Sonata VPN (набор https://t.me/addemoji/Sonata_VPN)

Как это работает
  • При старте бот читает набор через getStickerSet и берёт id эмодзи ПО ПОРЯДКУ В НАБОРЕ
    (см. PACK_ORDER ниже). К тому, какой обычный эмодзи привязан к стикеру в наборе,
    модуль больше не привязан — поэтому ничего не «теряется».
  • Перед отправкой каждого сообщения модуль заменяет обычные эмодзи на премиум:
    в тексте (HTML) — <tg-emoji>, на кнопках — иконка (icon_custom_emoji_id).
  • Если Telegram отклоняет сообщение с премиум-эмодзи, оно тут же уходит повторно
    с обычными. После 3 таких случаев модуль выключается и пишет админу.

Подключение (в боте), как и раньше:
    import premium_emoji
    ...
    async def main():
        ...
        init_db()
        await premium_emoji.setup(bot, dp, ADMIN_ID)

Команды для админа: /emoji_map  /emoji_test  /emoji_reload  /emoji_off  /emoji_on

Если добавите/переставите эмодзи в наборе — поправьте PACK_ORDER (порядок слева направо,
сверху вниз) и проверьте командой /emoji_test.
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

# Если нужно подменить конкретный id вручную: {"handshake": "5123456789012345678"}
MANUAL = {}

# ------------------------------------------------------------------------------------------
# 1. ПОРЯДОК ЭМОДЗИ В НАБОРЕ (как в Telegram: слева направо, сверху вниз). Всего 26.
# ------------------------------------------------------------------------------------------
PACK_ORDER = [
    "wave",           # 01 👋 приветствие
    "whitelist",      # 02 🛡 белые списки
    "book",           # 03 📖 книга
    "connect",        # 04 ⏻ подключиться
    "user",           # 05 👤 пользователь
    "card",           # 06 💳 карта
    "promo",          # 07 🎟 промокод
    "clock",          # 08 ⏰ будильник
    "bell_off",       # 09 🔕 отключить акции
    "phone",          # 10 📱 устройство
    "friends",        # 11 👥 друзья
    "link",           # 12 🔗 ссылка
    "sparkle",        # 13 ✨ искры
    "back",           # 14 ⬅ назад
    "cart",           # 15 🛒 корзина
    "rocket",         # 16 🚀 ракета
    "check",          # 17 ✅ галочка (активна / успешно)
    "bolt",           # 18 ⚡ молния (импорт)
    "qr",             # 19 🖼 QR-код
    "refresh",        # 20 🔄 обновить
    "calendar",       # 21 📅 календарь
    "clip",           # 22 📋 список / информация
    "globe",          # 23 🌍 глобус
    "cross",          # 24 ❌ крестик (не активна / ошибка)
    "handshake_alt",  # 25 🤝 рукопожатие (запасное, пока не используется)
    "handshake",      # 26 🤝 рукопожатие
]


def pick_ids(rows):
    """rows: [(эмодзи_привязки, custom_emoji_id), ...] в порядке набора -> {ключ: id}"""
    if len(rows) != len(PACK_ORDER):
        logging.warning(f"[EMOJI] В наборе {len(rows)} эмодзи, а в PACK_ORDER {len(PACK_ORDER)} — "
                        "проверьте порядок командой /emoji_test")
    out = {key: rows[i][1] for i, key in enumerate(PACK_ORDER) if i < len(rows)}
    out.update({k: v for k, v in MANUAL.items() if v})
    return out


# ------------------------------------------------------------------------------------------
# 2. ПРАВИЛА ЗАМЕНЫ
# ------------------------------------------------------------------------------------------
# Простые: один и тот же значок везде заменяется на один и тот же премиум (текст и кнопки).
SIMPLE = {
    "👋": "wave", "🖥": "whitelist", "📖": "book", "📲": "connect", "👤": "user",
    "💳": "card", "🎟": "promo", "⏰": "clock", "🔕": "bell_off", "📱": "phone",
    "👥": "friends", "🔗": "link", "✨": "sparkle", "⬅": "back", "🛒": "cart",
    "🚀": "rocket", "✅": "check", "⚡": "bolt", "🖼": "qr", "🔄": "refresh", "🔁": "refresh",
    "📅": "calendar", "📆": "calendar", "📋": "clip", "🌍": "globe",
    "❌": "cross", "🛑": "cross", "🤝": "handshake",
}

# По контексту: заменяются только в тексте и только если сразу за ними идут эти слова.
_PRE = r"\s*(?:<[^>]+>\s*)*"      # пробелы и теги <b>, <i> между эмодзи и словом
CONTEXT = {
    "🟢": (re.compile(_PRE + r"(?:Активна|∞)"), "check"),                 # статус подписки: активна / безлимит
    "🔴": (re.compile(_PRE + r"Не активна"), "cross"),                    # статус подписки: не активна
    "⏳": (re.compile(_PRE + r"Подписка скоро закончится"), "clock"),      # уведомление за 3 дня
    "🔔": (re.compile(_PRE + r"Подписка заканчивается"), "clock"),         # уведомление за 3 часа
}

# Кнопки без эмодзи в тексте, но с премиум-иконкой (точное совпадение текста)
PLAIN_BUTTONS = {"Подключиться": "connect"}

_CHARS = sorted(list(SIMPLE) + list(CONTEXT), key=len, reverse=True)
# Сначала «пропускаемые» куски (уже готовый <tg-emoji>, <pre>, <code>, любой тег), потом сам эмодзи
_TEXT_RE = re.compile(
    r"(<tg-emoji\b.*?</tg-emoji>|<pre\b.*?</pre>|<code\b.*?</code>|<[^>]*>)|("
    + "|".join(re.escape(c) for c in _CHARS) + r")\ufe0f?",
    re.S,
)
_BTN_RE = re.compile(r"^(" + "|".join(re.escape(c) for c in SIMPLE) + r")\ufe0f?\s*(.+)$", re.S)

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

    def sub(m):
        if m.group(1):                       # тег / код / уже готовый premium — не трогаем
            return m.group(0)
        ch = m.group(2)
        if ch in CONTEXT:
            rx, key = CONTEXT[ch]
            if not rx.match(s, m.end()):
                return m.group(0)
        else:
            key = SIMPLE[ch]
        cid = IDS.get(key)
        if not cid:
            return m.group(0)
        return f'<tg-emoji emoji-id="{cid}">{m.group(0)}</tg-emoji>'

    return _TEXT_RE.sub(sub, s)


def decorate_button_text(text):
    """(новый_текст, id) или None, если у кнопки нет премиум-замены"""
    text = text or ""
    key = PLAIN_BUTTONS.get(text.strip())
    if key and IDS.get(key):
        return text.strip(), IDS[key]
    m = _BTN_RE.match(text)
    if m:
        cid = IDS.get(SIMPLE[m.group(1)])
        if cid:
            return m.group(2), cid
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
        found = [(s.emoji or "", s.custom_emoji_id) for s in st.stickers if s.custom_emoji_id]
        ROWS = [(i, ch, cid) for i, (ch, cid) in enumerate(found)]
        IDS = pick_ids(found)
        try:
            os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({"ids": IDS, "rows": ROWS}, f, ensure_ascii=False)
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
    needed = set(SIMPLE.values()) | {v[1] for v in CONTEXT.values()} | set(PLAIN_BUTTONS.values())
    missing = sorted(k for k in needed if k not in IDS)
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
    lines = ["Тест порядка: слева — эмодзи из набора, справа — его роль в боте.\n"]
    for i, _ch, c in ROWS:
        name = PACK_ORDER[i] if i < len(PACK_ORDER) else "— (нет в PACK_ORDER)"
        lines.append(f'<tg-emoji emoji-id="{c}">⭐</tg-emoji> {i + 1:02d} {name}')
    lines.append("\nЕсли вместо анимированных значков обычные ⭐, то у владельца бота нет Telegram Premium.")
    try:
        await message.bot.send_message(
            message.chat.id, "\n".join(lines), parse_mode="HTML",
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