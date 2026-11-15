"""Еркін — гайд сату боты (Vercel, webhook режимі). Компьютер қажет емес.

Vercel → Settings → Environment Variables:
  BOT_TOKEN, ADMIN_ID, CHANNEL_ID, KASPI_LINK, WEBHOOK_SECRET
  (міндетті емес) PRICE, OFERTA_URL
Сатып алушылар тізімі: Vercel → Storage → Upstash Redis (KV_REST_API_URL / KV_REST_API_TOKEN өзі қосылады).

Бір рет іске қосу: браузерде ашыңыз
  https://<сайт>/api/bot?setup=<WEBHOOK_SECRET>
"""
import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler

E = os.environ.get
BOT_TOKEN = E("BOT_TOKEN", "")
ADMIN_ID = int(E("ADMIN_ID", "0") or 0)
CHANNEL_ID = int(E("CHANNEL_ID", "0") or 0) or None
KASPI_LINK = E("KASPI_LINK", "")
PRICE = E("PRICE", "") or "5 000 ₸"
OFERTA_URL = E("OFERTA_URL", "") or "https://erkin-target-guide.vercel.app/oferta.html"
SECRET = E("WEBHOOK_SECRET", "")
KV_URL = E("KV_REST_API_URL") or E("UPSTASH_REDIS_REST_URL") or ""
KV_TOKEN = E("KV_REST_API_TOKEN") or E("UPSTASH_REDIS_REST_TOKEN") or ""
API = f"https://api.telegram.org/bot{BOT_TOKEN}/"


# ---------- Telegram ----------
def tg(method, **params):
    data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
            for k, v in params.items() if v is not None}
    req = urllib.request.Request(API + method, data=urllib.parse.urlencode(data).encode())
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            res = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        res = json.loads(e.read().decode() or "{}")
    except Exception as e:
        print("tg error", method, e)
        return None
    if not res.get("ok"):
        print("tg not ok", method, res.get("description"))
        return None
    return res["result"]


def send(chat_id, text, kb=None, html=False):
    return tg("sendMessage", chat_id=chat_id, text=text, reply_markup=kb,
              parse_mode="HTML" if html else None, disable_web_page_preview="true")


# ---------- деректер (Upstash Redis) ----------
def kv(*cmd):
    if not KV_URL:
        return None
    req = urllib.request.Request(KV_URL, data=json.dumps(list(cmd)).encode(),
                                 headers={"Authorization": f"Bearer {KV_TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode()).get("result")
    except Exception as e:
        print("kv error", e)
        return None


def get_buyer(uid):
    v = kv("HGET", "buyers", str(uid))
    return json.loads(v) if v else {}


def set_buyer(uid, **fields):
    b = get_buyer(uid); b.update(fields)
    kv("HSET", "buyers", str(uid), json.dumps(b, ensure_ascii=False))


def channel_id():
    return CHANNEL_ID or (int(kv("GET", "channel_id")) if kv("GET", "channel_id") else None)


# ---------- мәтіндер ----------
STEP1 = (f"1️⃣ Төмендегі <b>Kaspi арқылы төлеу</b> батырмасын басып, {PRICE} төлеңіз.\n" if KASPI_LINK
         else f"1️⃣ Kaspi арқылы {PRICE} төлеңіз.\n")
OFFER = (
    "Сәлем! 👋 Бұл — Еркіннің ресми боты.\n\n"
    "<b>📘 Таргет + Claude гайды</b>\n"
    "• 9 бөлімнен тұратын гайд (қазақша, PDF)\n"
    "• 6 дайын Claude скилі (Reels монтажы да бар)\n"
    "• Промпт кітапханасы мен чек-лист\n"
    "• Жабық Telegram канал, жаңартулар тегін\n\n"
    f"💰 Бағасы: <b>{PRICE}</b> · бір рет төлем\n\n"
    "<b>Қалай алуға болады:</b>\n" + STEP1 +
    "2️⃣ Kaspi чегін (скриншот немесе PDF) <b>осы чатқа</b> жіберіңіз.\n"
    "3️⃣ Төлем расталған соң осы чатқа <b>жабық каналдың жеке сілтемесі</b> келеді.\n\n"
    "ℹ️ Claude жазылымы (Pro) пакетке кірмейді, оны claude.com сайтынан өзіңіз рәсімдейсіз.\n"
    f"📄 Төлем жасау арқылы <a href=\"{OFERTA_URL}\">жария оферта</a> шарттарымен келісесіз."
)


def offer_kb():
    rows = []
    if KASPI_LINK:
        rows.append([{"text": f"💳 Kaspi арқылы төлеу — {PRICE}", "url": KASPI_LINK}])
    rows.append([{"text": "🧾 Төледім — чек жіберемін", "callback_data": "paid"}])
    return {"inline_keyboard": rows}


def admin_kb(uid):
    return {"inline_keyboard": [[{"text": "✅ Растау", "callback_data": f"ok:{uid}"},
                                 {"text": "❌ Бас тарту", "callback_data": f"no:{uid}"}]]}


def send_invite(uid):
    ch = channel_id()
    if not ch:
        send(ADMIN_ID, "⚠️ CHANNEL_ID баптауы жоқ. Vercel-де CHANNEL_ID қосыңыз.")
        return False
    link = tg("createChatInviteLink", chat_id=ch, member_limit=1, name=f"buyer {uid}")
    if not link:
        send(ADMIN_ID, "⚠️ Сілтеме жасалмады. Бот каналда әкімші ме және «Шақыру сілтемелері» құқығы бар ма, тексеріңіз.")
        return False
    send(uid, "✅ Төлем расталды! Жабық каналға кіру сілтемесі (тек сізге, бір рет жұмыс істейді):\n"
              f"{link['invite_link']}\n\nКаналдағы бекітілген хабарламадан бастаңыз.")
    return True


# ---------- өңдеушілер ----------
def on_message(m):
    if m["chat"].get("type") != "private":
        return
    u = m["from"]; uid = u["id"]; text = m.get("text", "")
    name = " ".join(x for x in [u.get("first_name"), u.get("last_name")] if x)
    uname = u.get("username") or "—"
    if text.startswith("/start"):
        send(uid, OFFER, offer_kb(), html=True); return
    if text.startswith("/help"):
        send(uid, "Чектің скринін (фото немесе PDF) осы чатқа жіберіңіз. Сұрақ болса: @rkn24"); return
    if text.startswith("/link"):
        if get_buyer(uid).get("status") == "paid":
            send_invite(uid)
        elif not KV_URL:
            send(uid, "Сілтемені қайта алу үшін @rkn24-ке жазыңыз.")
        else:
            send(uid, "Төлем әлі расталмаған. Чекті осы чатқа жіберіңіз.")
        return
    if text.startswith("/stats") and uid == ADMIN_ID:
        allb = kv("HGETALL", "buyers") or []
        vals = [json.loads(allb[i + 1]) for i in range(0, len(allb), 2)]
        paid = sum(1 for v in vals if v.get("status") == "paid")
        pend = sum(1 for v in vals if v.get("status") == "pending")
        send(uid, f"Сатып алғандар: {paid}\nКүтуде: {pend}" + ("" if KV_URL else "\n(дерекқор қосылмаған)")); return
    if "photo" in m or "document" in m:
        if get_buyer(uid).get("status") == "paid":
            send(uid, "Сіздің төлеміңіз бұрын расталған. Сілтеме жоғалса, /link деп жазыңыз."); return
        caption = f"🧾 Жаңа чек\nАты: {name}\nUsername: @{uname}\nID: {uid}"
        if "photo" in m:
            tg("sendPhoto", chat_id=ADMIN_ID, photo=m["photo"][-1]["file_id"], caption=caption, reply_markup=admin_kb(uid))
        else:
            tg("sendDocument", chat_id=ADMIN_ID, document=m["document"]["file_id"], caption=caption, reply_markup=admin_kb(uid))
        set_buyer(uid, name=name, username=uname, status="pending")
        send(uid, "✅ Чек қабылданды! Тексеріп жатырмын, әдетте бірнеше минут.\nРасталған соң жабық каналдың сілтемесі осы чатқа келеді.")
        return
    if text and uid != ADMIN_ID:
        send(ADMIN_ID, f"💬 {name} (@{uname}, ID {uid}):\n{text}")
        send(uid, "Хабарламаңыз Еркінге жіберілді. Сатып алу үшін /start басыңыз.")


def on_callback(c):
    tg("answerCallbackQuery", callback_query_id=c["id"])
    if c.get("data") == "paid":
        send(c["from"]["id"], "Kaspi чегін скриншот немесе PDF файл ретінде осы чатқа жіберіңіз 👇"); return
    if c["from"]["id"] != ADMIN_ID:
        return
    action, uid = c["data"].split(":"); uid = int(uid); msg = c["message"]
    if action == "ok":
        if not send_invite(uid):
            return
        set_buyer(uid, status="paid"); mark = "✅ РАСТАЛДЫ"
    else:
        send(uid, "Өкінішке қарай, төлем табылмады. Чекті қайта тексеріп жіберіңіз немесе осында жазыңыз.")
        set_buyer(uid, status="rejected"); mark = "❌ БАС ТАРТЫЛДЫ"
    tg("editMessageCaption", chat_id=msg["chat"]["id"], message_id=msg["message_id"],
       caption=(msg.get("caption") or "") + "\n\n" + mark)


def on_update(up):
    if "message" in up:
        on_message(up["message"])
    elif "callback_query" in up:
        on_callback(up["callback_query"])
    elif "channel_post" in up and not CHANNEL_ID:
        kv("SET", "channel_id", str(up["channel_post"]["chat"]["id"]))


# ---------- Vercel handler ----------
class handler(BaseHTTPRequestHandler):
    def _reply(self, code, text):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode())

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if not SECRET or q.get("setup", [""])[0] != SECRET:
            return self._reply(200, "Бот жұмыс істеп тұр.")
        host = self.headers.get("x-forwarded-host") or self.headers.get("host")
        url = f"https://{host}/api/bot"
        r1 = tg("setWebhook", url=url, secret_token=SECRET, drop_pending_updates="true",
                allowed_updates=["message", "callback_query", "channel_post"])
        r2 = tg("setMyCommands", commands=[{"command": "start", "description": "Гайд туралы және сатып алу"},
                                           {"command": "link", "description": "Каналдың сілтемесін қайта алу"},
                                           {"command": "help", "description": "Көмек"}])
        me = tg("getMe") or {}
        lines = [f"Бот: @{me.get('username', '?')}", f"Webhook: {'✅ қосылды' if r1 else '❌ қате (BOT_TOKEN тексеріңіз)'} → {url}",
                 f"Мәзір: {'✅' if r2 else '❌'}", f"Админ ID: {ADMIN_ID or '❌ жоқ'}", f"Канал ID: {CHANNEL_ID or '❌ жоқ'}",
                 f"Kaspi сілтемесі: {'✅' if KASPI_LINK else '❌ жоқ'}", f"Дерекқор: {'✅ қосылған' if KV_URL else '⚠️ қосылмаған'}"]
        self._reply(200, "\n".join(lines))

    def do_POST(self):
        if SECRET and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET:
            return self._reply(403, "forbidden")
        n = int(self.headers.get("content-length") or 0)
        try:
            up = json.loads(self.rfile.read(n).decode() or "{}")
            on_update(up)
        except Exception as e:
            print("update error", e)
        self._reply(200, "ok")
