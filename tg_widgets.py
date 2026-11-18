# -*- coding: utf-8 -*-
"""
tg_widgets.py — виджеты Telegram (Bot API 10.4) для Sonata VPN: интерактивные карточки прямо внутри сообщения.
  1) «Подключиться»: выбор ОС -> приложения -> импорт подписки, без перезагрузки экранов (быстро, всё в одном сообщении).
  2) Проверка на бота при регистрации (вместо 4 кнопок-животных).
Кладётся рядом с файлом бота (рядом с miniapp_api.py, который он использует). Подключение — см. подсказки в ответе.

Важно: виджеты в продакшене Telegram работают ТОЛЬКО в личном чате с ботом, а сам код виджета — не более 32 КБ и 4 КБ после сжатия.
Если что-то пошло не так (старый клиент Telegram, ошибка API) — отправка вернёт False, и бот пойдёт по прежнему сценарию.
"""
import asyncio, json, logging, random, sqlite3, time, zlib
from types import SimpleNamespace
import aiohttp
from aiogram import BaseMiddleware, F
from aiogram.filters import Command

import miniapp_api

G: dict = {}
CHANNEL_URL = "https://t.me/Sonata_Information"

# ───────────────────────────── HTML виджетов ─────────────────────────────
# Цвета — переменные темы чата (светлая/тёмная), фирменный жёлтый #ffd60a — только на главных кнопках.
CAPTCHA_HTML = r'''<style>
body{margin:0;padding:14px;text-align:center}
h3{margin:0 0 4px;font-size:17px}
.q{color:var(--tg-theme-hint-color);font-size:14px;margin-bottom:12px}
.q b{color:var(--tg-theme-text-color);font-size:16px}
.g{display:flex;gap:8px}
.e{flex:1;height:62px;border:0;border-radius:16px;font-size:30px;background:var(--tg-theme-secondary-bg-color);animation:p .4s both}
.e:active{transform:scale(.9)}
.m{height:18px;margin-top:10px;font-size:13px;color:var(--tg-theme-hint-color)}
.sh{animation:s .4s}
svg{display:block;margin:4px auto 8px}
.c,.k{fill:none;stroke:#34c759;stroke-linecap:round;stroke-width:3}
.c{stroke-dasharray:151;stroke-dashoffset:151;animation:d .6s forwards}
.k{stroke-width:4;stroke-dasharray:40;stroke-dashoffset:40;animation:d .4s .5s forwards}
@keyframes d{to{stroke-dashoffset:0}}
@keyframes p{from{transform:scale(.5)}}
@keyframes s{25%{transform:translateX(-8px)}75%{transform:translateX(8px)}}
</style><div id=a></div><script>
var W=window.TelegramWidget,a=document.getElementById('a'),busy=0;
function D(){try{return JSON.parse(W.chatData)||{}}catch(e){return{}}}
function draw(x){var d=x||D();a.className='';
if(d.s==='ok'){a.innerHTML='<svg width=64 height=64 viewBox="0 0 52 52"><circle class=c cx=26 cy=26 r=24 /><path class=k d="M15 27l8 8 14-16"/></svg><h3>Проверка пройдена</h3><div class=q>Открываем меню…</div>';return}
if(d.s==='fail'){a.innerHTML='<h3>Не получилось</h3><div class=q>Слишком много ошибок или сессия устарела. Нажмите /start, чтобы начать заново.</div>';return}
if(!d.o){a.innerHTML='<div class=q>Загрузка…</div>';return}
a.innerHTML='<h3>Вы не бот?</h3><div class=q>Нажмите на животное: <b>'+d.q+'</b></div><div class=g>'+d.o.map(function(e,i){return'<button class=e style="animation-delay:'+i*70+'ms" onclick="t('+i+')">'+e+'</button>'}).join('')+'</div><div class=m id=m>'+(d.t?'Неверно — попробуйте ещё раз':'')+'</div>'}
function t(i){if(busy)return;busy=1;W.HapticFeedback.impactOccurred('light');document.getElementById('m').textContent='Проверяем…';
W.request('k:'+i).then(function(r){busy=0;var v=r.result;
if(v==='ok'){W.HapticFeedback.notificationOccurred('success');draw({s:'ok'})}
else if(v==='no'){W.HapticFeedback.notificationOccurred('error');setTimeout(function(){a.className='sh'},30)}
else draw({s:'fail'})},function(e){busy=0;document.getElementById('m').textContent=e.code==='RATE_LIMITED'?'Не так быстро…':'Ошибка связи, попробуйте ещё раз'})}
W.onEvent('chatDataChanged',function(){draw()});draw();
</script>'''

CONNECT_HTML = r'''<style>
body{margin:0;padding:14px}
h3{margin:0 0 6px;font-size:17px}
.q{color:var(--tg-theme-hint-color);font-size:14px;margin-bottom:10px;line-height:1.3}
.g{display:grid;grid-template-columns:1fr 1fr;gap:6px}
button{width:100%;height:38px;border:0;border-radius:12px;font-size:14px;color:var(--tg-theme-text-color);background:var(--tg-theme-secondary-bg-color);animation:p .3s both}
button:active{transform:scale(.95)}
.w{grid-column:1/3}
.y{height:44px;margin-bottom:8px;font-weight:700;color:#1b1500;background:#ffd60a}
.b{margin-top:8px;color:var(--tg-theme-hint-color);background:none}
.sp{width:34px;height:34px;margin:34px auto 12px;border:4px solid var(--tg-theme-secondary-bg-color);border-top-color:#ffd60a;border-radius:50%;animation:r .8s linear infinite}
.z{text-align:center}
svg{display:block;margin:0 auto 6px}
.c,.k{fill:none;stroke:#34c759;stroke-linecap:round;stroke-width:3}
.c{stroke-dasharray:151;stroke-dashoffset:151;animation:d .5s forwards}
.k{stroke-width:4;stroke-dasharray:40;stroke-dashoffset:40;animation:d .4s .4s forwards}
@keyframes d{to{stroke-dashoffset:0}}
@keyframes p{from{transform:scale(.85)}}
@keyframes r{to{transform:rotate(360deg)}}
</style><div id=a></div><script>
var W=window.TelegramWidget,a=document.getElementById('a'),busy=0,U='',S='',d={};
try{d=JSON.parse(W.chatData)||{}}catch(e){}
var O=[['ios','iPhone / iPad'],['and','Android'],['win','Windows'],['mac','macOS'],['lin','Linux'],['atv','Apple TV'],['antv','Android TV']];
var A={ios:'Happ,Streisand,Karing,INCY',and:'Happ,v2rayNG,INCY,Karing',win:'Happ,v2rayN,Nekobox,Karing,INCY',mac:'Happ,Sing-Box,FoXray,V2RayXS,Karing,INCY',lin:'Happ,Nekobox,Sing-Box,v2rayN,Karing',atv:'Happ',antv:'Happ'};
function B(t,f,c){return'<button'+(c?' class='+c:'')+' onclick="'+f+'">'+t+'</button>'}
function os(){if(d.d===0){a.innerHTML='<h3>Подписка не активна</h3><div class=q>Оформите тариф кнопкой «Купить подписку» в меню бота — и вернитесь сюда.</div>';return}
a.innerHTML='<h3>Выберите устройство</h3><div class=g>'+O.map(function(o,i){return B(o[1],"ap('"+o[0]+"')",i==6?'w':'')}).join('')+'</div>'}
function ap(o){var n=O.filter(function(x){return x[0]==o})[0][1];
a.innerHTML='<h3>'+n+'</h3><div class=q>Выберите приложение. Рекомендуем Happ.</div><div class=g>'+A[o].split(',').map(function(p){return B(p+(p=='Happ'?' ★':''),"go('"+o+"','"+p.toLowerCase().replace('-','')+"','"+p+"')")}).join('')+'</div>'+B('← Назад','os()','b')}
function go(o,c,n){if(busy)return;busy=1;W.HapticFeedback.impactOccurred('light');
W.request('c:'+o+':'+c).then(function(r){busy=0;var j={};try{j=JSON.parse(r.result)}catch(e){}
if(j.u){U=j.u;S=j.s;dn(n)}else if(j.tv)tv();else if(j.ch)ch();else er(j.e)},function(e){busy=0;er(e.code==='RATE_LIMITED'?'Не так быстро…':'Нет связи с ботом, попробуйте ещё раз')});
a.innerHTML='<div class=sp></div><div class="q z">Готовим подписку…</div>'}
function dn(n){W.HapticFeedback.notificationOccurred('success');
a.innerHTML='<svg width=48 height=48 viewBox="0 0 52 52"><circle class=c cx=26 cy=26 r=24 /><path class=k d="M15 27l8 8 14-16"/></svg><h3 class=z>Готово!</h3><div class="q z">Нажмите, чтобы добавить подписку в '+n+'</div>'+B('Импортировать в '+n,'W.openLink(U)','y')+'<div class=g>'+B('Скопировать ссылку','W.copyText(S)')+B('Другое устройство','os()')+'</div>'}
function tv(){a.innerHTML='<h3>Код с экрана ТВ</h3><div class=q>Откройте Happ на ТВ → Web Import. Затем отправьте 5-значный код сообщением в этот чат — я передам подписку на телевизор.</div>'+B('← Назад','os()','b')}
function ch(){a.innerHTML='<h3>Подпишитесь на канал</h3><div class=q>Там важные новости и промокоды. После подписки нажмите «Назад» и выберите устройство снова.</div>'+B('Открыть канал','W.openTelegramLink(\'__CH__\')','y')+B('← Назад','os()','b')}
function er(m){a.innerHTML='<h3>Не получилось</h3><div class=q>'+String(m||'Ошибка').replace(/</g,'&lt;')+'</div>'+B('← Назад','os()','b')}
os();
</script>'''.replace("__CH__", CHANNEL_URL)

for _n, _h in (("captcha", CAPTCHA_HTML), ("connect", CONNECT_HTML)):   # сервер Telegram считает размер именно так
    _z = len(zlib.compress(_h.encode("utf-8"), 9))
    if _z > 4096 or len(_h.encode("utf-8")) > 32768:
        logging.error(f"[WIDGET] виджет {_n}: {_z} байт после сжатия — больше лимита 4096, Telegram его не примет!")


# ───────────────────────────── Bot API ─────────────────────────────
async def _api(method, payload):
    url = f"https://api.telegram.org/bot{G['token']}/{method}"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as r:
            d = await r.json(content_type=None)
    if not d.get("ok"):
        raise RuntimeError(f"{method}: {d.get('description')}")
    return d["result"]


def _j(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


# ───────────────────────────── сессии проверки (переживают перезапуск бота) ─────────────────────────────
def _db():
    c = sqlite3.connect(G["db"], timeout=30.0)
    c.execute("CREATE TABLE IF NOT EXISTS tgw_sessions(chat_id INTEGER, message_id INTEGER, kind TEXT, user_id INTEGER, data TEXT, ts INTEGER, PRIMARY KEY(chat_id, message_id))")
    return c


def _sess_put(cid, mid, kind, uid, data):
    c = _db()
    try:
        c.execute("DELETE FROM tgw_sessions WHERE ts<?", (int(time.time()) - 86400,))
        c.execute("INSERT OR REPLACE INTO tgw_sessions VALUES(?,?,?,?,?,?)", (cid, mid, kind, uid, _j(data), int(time.time())))
        c.commit()
    finally:
        c.close()


def _sess_get(cid, mid):
    c = _db()
    try:
        r = c.execute("SELECT kind, user_id, data FROM tgw_sessions WHERE chat_id=? AND message_id=?", (cid, mid)).fetchone()
    finally:
        c.close()
    return {"kind": r[0], "user_id": r[1], "data": json.loads(r[2])} if r else None


def _sess_del(cid, mid):
    c = _db()
    try:
        c.execute("DELETE FROM tgw_sessions WHERE chat_id=? AND message_id=?", (cid, mid)); c.commit()
    finally:
        c.close()


# ───────────────────────────── проверка на бота ─────────────────────────────
def _challenge():
    m = G["ANIMAL_MAP"]
    opts = random.sample(list(m), 4)
    ans = random.randrange(4)
    return {"q": m[opts[ans]], "o": opts}, ans


async def send_captcha_widget(chat_id: int, user_id: int, ref_arg: str) -> bool:
    """Отправляет виджет-проверку. True — отправлено; False — виджеты недоступны (вызывающий код использует старую капчу)."""
    try:
        ch, ans = _challenge()
        kb = {"inline_keyboard": [[{"text": "🔁 Не отображается? Обычная проверка", "callback_data": f"capold:{ref_arg}"[:64]}]]}
        msg = await _api("sendWidget", {"chat_id": chat_id, "html": CAPTCHA_HTML, "allow_queries": True, "width": 0, "height": 190,
                                        "chat_data": _j({**ch, "t": 0}), "caption": "🔐 Проверка безопасности — нажмите на нужное животное", "reply_markup": kb})
        _sess_put(chat_id, msg["message_id"], "cap", user_id, {"ans": ans, "ref": ref_arg, "t": 0})
        return True
    except Exception as e:
        logging.warning(f"[WIDGET] капча-виджет не отправлен, используем обычную: {e}")
        return False


async def send_old_captcha(chat_id: int, ref_arg: str):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    m = G["ANIMAL_MAP"]
    animals = random.sample(list(m), 4)
    correct = random.choice(animals)
    kb = InlineKeyboardBuilder()
    for an in animals:
        kb.button(text=an, callback_data=f"captcha:{'yes' if an == correct else 'no'}:{ref_arg}")
    kb.adjust(4)
    await G["bot"].send_message(chat_id, f"<b>Добро пожаловать! Пройдите верификацию.</b>\n\nВыбери животное: <b>{m[correct]}</b>",
                                reply_markup=kb.as_markup(), parse_mode="HTML")


async def _on_capold(callback):
    ref = callback.data.split(":", 1)[1] if ":" in callback.data else "none"
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await send_old_captcha(callback.message.chat.id, ref)


class _Msg:
    """Подмена message для process_captcha: настоящее сообщение — виджет, его нельзя править как текст."""
    def __init__(s, cid, mid):
        s.chat, s.message_id = SimpleNamespace(id=cid, type="private"), mid

    async def delete(s):
        try:
            await G["bot"].delete_message(s.chat.id, s.message_id)
        except Exception:
            pass

    async def edit_text(s, text="", **k):
        try:
            await G["bot"].send_message(s.chat.id, text, **{x: v for x, v in k.items() if x == "parse_mode"})
        except Exception:
            pass
        await s.delete()

    async def answer(s, *a, **k):
        return await G["bot"].send_message(s.chat.id, *a, **k)


class _CB:
    def __init__(s, frm, cid, mid, data):
        s.from_user = SimpleNamespace(id=int(frm["id"]), username=frm.get("username"), first_name=frm.get("first_name", ""))
        s.data, s.bot, s.message = data, G["bot"], _Msg(cid, mid)

    async def answer(s, *a, **k):
        return None


async def _captcha_pass(frm, cid, mid, ref):
    await asyncio.sleep(1.4)          # дать виджету дорисовать галочку
    try:
        await G["process_captcha"](_CB(frm, cid, mid, f"captcha:yes:{ref}"))
    except Exception as e:
        logging.error(f"[WIDGET] регистрация после проверки: {e}", exc_info=True)


async def _captcha_answer(frm, cid, mid, idx):
    uid = int(frm["id"])
    s = _sess_get(cid, mid)
    if not s:
        await asyncio.sleep(0.6); s = _sess_get(cid, mid)      # на случай гонки с записью сессии
    if not s or s["kind"] != "cap" or s["user_id"] != uid:
        return "x"
    d = s["data"]
    if idx == d["ans"]:
        _sess_del(cid, mid)
        asyncio.create_task(_captcha_pass(frm, cid, mid, d["ref"]))
        return "ok"
    d["t"] += 1
    if d["t"] >= 3:
        _sess_del(cid, mid)
        await _api("editMessageWidgetData", {"chat_id": cid, "message_id": mid, "chat_data": _j({"s": "fail"})})
        return "fail"
    ch, d["ans"] = _challenge()
    _sess_put(cid, mid, "cap", uid, d)
    await _api("editMessageWidgetData", {"chat_id": cid, "message_id": mid, "chat_data": _j({**ch, "t": d["t"]})})
    return "no"


# ───────────────────────────── «Подключиться» ─────────────────────────────
async def send_connect_widget(chat_id: int, user_id: int) -> bool:
    """True — виджет выбора устройства отправлен; False — используйте прежний сценарий."""
    try:
        u = G["get_user_from_db"](user_id)
        exp = int(u[4] or 0) if u else 0
        left = int((exp - time.time() + 86399) // 86400) if exp > time.time() else 0
        kb = {"inline_keyboard": [[{"text": "⬅️ Назад", "callback_data": "back"}], [{"text": "🔁 Не отображается? Обычное меню", "callback_data": "connect_old"}]]}
        await _api("sendWidget", {"chat_id": chat_id, "html": CONNECT_HTML, "allow_queries": True, "width": 0, "height": 300,
                                  "chat_data": _j({"d": left}), "caption": "📲 Подключение к Sonata VPN", "reply_markup": kb})
        return True
    except Exception as e:
        logging.warning(f"[WIDGET] виджет подключения не отправлен, используем обычный: {e}")
        return False


async def _tv_prompt(uid: int, os_: str, sub_url: str):
    """ТВ: код вводится сообщением (в виджетах нет клавиатуры) — включаем прежнее состояние ожидания кода."""
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.storage.base import StorageKey
    bot = G["bot"]
    ctx = FSMContext(storage=G["dp"].fsm.storage, key=StorageKey(bot_id=bot.id, chat_id=uid, user_id=uid))
    await ctx.update_data(sub_id=sub_url.rsplit("/", 1)[-1])
    await ctx.set_state(G["AppleTVState"].waiting_for_code if os_ == "atv" else G["AndroidTVState"].waiting_for_code)
    name = "Apple TV" if os_ == "atv" else "Android TV"
    await bot.send_message(uid, f"📺 <b>Настройка Happ на {name}</b>\n\n1. Откройте <b>Happ</b> на телевизоре → <b>Web Import</b>.\n"
                                "2. На экране появится код.\n\n✍️ <b>Напишите этот код сообщением в чат:</b>", parse_mode="HTML",
                           reply_markup=G["InlineKeyboardMarkup"](inline_keyboard=[[G["InlineKeyboardButton"](text="❌ Отмена", callback_data="connect")]]))


async def _connect_answer(frm, data):
    try:
        _, os_, app = data.split(":", 2)
    except ValueError:
        return _j({"e": "Некорректный запрос"})
    uid = int(frm["id"])
    tg = {"id": uid, "username": frm.get("username") or "", "first_name": frm.get("first_name") or ""}
    r = await miniapp_api.m_connect(uid, tg, {"os": os_, "app": app})
    if r.get("need_channel"):
        return _j({"ch": 1})
    if not r.get("ok"):
        return _j({"e": r.get("error") or "Ошибка"})
    if r.get("tv"):
        await _tv_prompt(uid, os_, r["sub_url"])
        return _j({"tv": 1})
    return _j({"u": r["url"], "s": r["sub_url"]})


# ───────────────────────────── приём widget_query ─────────────────────────────
async def _on_query(wq: dict):
    qid, data = str(wq.get("id")), str(wq.get("data") or "")
    logging.info(f"[WIDGET] получен widget_query: data={data!r}")
    frm, chat = wq.get("from") or {}, wq.get("chat") or {}
    res = None
    try:
        cid, mid, uid = int(chat.get("id", 0)), int(wq.get("message_id", 0)), int(frm.get("id", 0))
        if not uid or cid != uid:
            res = "x"
        elif data.startswith("k:"):
            res = await _captcha_answer(frm, cid, mid, int(data[2:]))
        elif data.startswith("c:"):
            res = await _connect_answer(frm, data)
    except Exception as e:
        logging.error(f"[WIDGET] ошибка обработки запроса: {e}", exc_info=True)
        res = _j({"e": "Внутренняя ошибка, попробуйте ещё раз"}) if data.startswith("c:") else None
    try:                                    # на КАЖДЫЙ запрос нужно ответить за 15 секунд, иначе у виджета будет TIMEOUT
        await _api("answerWidgetQuery", {"widget_query_id": qid, **({"data": res} if res else {})})
    except Exception as e:
        logging.error(f"[WIDGET] answerWidgetQuery: {e}")


class _WidgetMiddleware(BaseMiddleware):
    """aiogram не знает апдейт widget_query и молча его выбрасывает — перехватываем до диспетчера."""
    async def __call__(self, handler, event, data):
        wq = getattr(event, "widget_query", None)
        if wq is None:
            wq = (getattr(event, "model_extra", None) or {}).get("widget_query")
        if wq is not None:
            if hasattr(wq, "model_dump"):
                wq = wq.model_dump(exclude_none=True)
            asyncio.create_task(_on_query(wq))
            return None
        return await handler(event, data)


async def _cmd_wtest(message):
    """/wtest — только для создателя: показывает, почему виджет не отправляется."""
    if message.from_user.id != G.get("admin"):
        return
    rep = [f"aiogram: {__import__('aiogram').__version__}", f"setup выполнен: {'да' if G.get('token') else 'НЕТ'}"]
    for name, html, data in (("connect", CONNECT_HTML, {"d": 5}), ("captcha", CAPTCHA_HTML, {"s": "ok"})):
        try:
            m = await _api("sendWidget", {"chat_id": message.chat.id, "html": html, "allow_queries": True, "width": 0, "height": 300,
                                          "chat_data": _j(data), "caption": f"тест: {name}"})
            rep.append(f"✅ {name}: отправлен (message_id {m.get('message_id')})")
        except Exception as e:
            rep.append(f"❌ {name}: {e}")
    await message.answer("\n".join(rep))


def allowed_updates(dp):
    """Передайте в dp.start_polling(bot, allowed_updates=...): иначе Telegram не пришлёт widget_query."""
    return list(dp.resolve_used_update_types()) + ["widget_query"]


def setup(dp, ns: dict):
    """Вызвать один раз в main() бота:  tg_widgets.setup(dp, globals())"""
    G.update({"admin": ns["ADMIN_ID"], "dp": dp, "bot": ns["bot"], "token": ns["API_TOKEN"], "db": ns["DB_PATH"], "ANIMAL_MAP": ns["ANIMAL_MAP"],
              "get_user_from_db": ns["get_user_from_db"], "process_captcha": ns["process_captcha"],
              "AppleTVState": ns["AppleTVState"], "AndroidTVState": ns["AndroidTVState"],
              "InlineKeyboardMarkup": ns["InlineKeyboardMarkup"], "InlineKeyboardButton": ns["InlineKeyboardButton"]})
    _db().close()
    dp.update.outer_middleware(_WidgetMiddleware())
    dp.callback_query.register(_on_capold, F.data.startswith("capold:"))
    dp.message.register(_cmd_wtest, Command("wtest"))
    logging.info("[WIDGET] виджеты подключены (Bot API 10.4)")