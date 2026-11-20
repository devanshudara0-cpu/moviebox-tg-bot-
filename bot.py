import os, json, subprocess, asyncio, re, html, io, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ["TELEGRAM_TOKEN"]
ADMIN_ID = 7641123461
DB = "users.json"
BRIDGE = os.path.abspath("tg_bridge")
FOOTER = "\n\n⚡ <i>Made by @Dara_OG</i>"
PROVIDERS = [
    ("moviebox", "MovieBox"), ("fourkhdhub", "4KHDHub"), ("dramachi", "Dramachi"),
    ("bdix_circleftp", "CircleFTP"), ("bdix_dhakaflix", "DhakaFlix"), ("addons", "Addons"),
]
SESSIONS = {}

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *args): pass

def start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    HTTPServer(("0.0.0.0", port), Health).serve_forever()

def esc(v): return html.escape(str(v or ""))
def load_users(): return set(json.load(open(DB))) if os.path.exists(DB) else {ADMIN_ID}
def save_users(u): json.dump(list(u), open(DB, "w"))
def allowed(uid): return uid == ADMIN_ID or uid in load_users()

async def run_bridge(*args):
    res = await asyncio.to_thread(subprocess.run, [BRIDGE, *args], capture_output=True, text=True, timeout=90)
    if res.returncode != 0: return {"error": res.stderr[:800] or "Bridge error"}
    return json.loads(res.stdout)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if allowed(uid):
        await update.message.reply_text(
            f"🎬 <b>MovieBox Stream Bot Ready!</b>\nSend any movie/series name (e.g. <code>Avatar</code>) or <code>/movie Avengers</code>.{FOOTER}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(f"🔒 <b>Access Denied</b>\nSend your ID to Admin: <code>{uid}</code>{FOOTER}", parse_mode="HTML")

async def allow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.args: return
    u = load_users(); u.add(int(context.args[0])); save_users(u)
    await update.message.reply_text(f"✅ Allowed: {context.args[0]}")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.args: return
    u = load_users(); u.discard(int(context.args[0])); save_users(u)
    await update.message.reply_text(f"🗑 Removed: {context.args[0]}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("👥 Allowed IDs: " + ", ".join(map(str, sorted(load_users()))))

async def do_search(msg_obj, uid, query, prov="moviebox", edit=False):
    SESSIONS[uid] = {"query": query, "prov": prov}
    data = await run_bridge("search", prov, query)
    results = data.get("results", [])[:10]
    SESSIONS[uid]["results"] = results
    r1 = [InlineKeyboardButton(f"{'✅ ' if k == prov else ''}{lbl}", callback_data=f"p:{k}") for k, lbl in PROVIDERS[:3]]
    r2 = [InlineKeyboardButton(f"{'✅ ' if k == prov else ''}{lbl}", callback_data=f"p:{k}") for k, lbl in PROVIDERS[3:]]
    kb = [r1, r2]
    if data.get("error"):
        text = f"🔎 <b>{esc(query)}</b> • <code>{prov}</code>\n❌ {esc(data['error'])}{FOOTER}"
    elif not results:
        text = f"🔎 <b>{esc(query)}</b> • <code>{prov}</code>\n😕 No results found. Try another server:{FOOTER}"
    else:
        text = f"🍿 <b>Search Results</b> • <code>{prov}</code>\n🔎 <i>{esc(query)}</i>\n\nPick a title below:{FOOTER}"
        for i, item in enumerate(results):
            yr = f" ({item['year']})" if item.get("year") else ""
            tp = "📺" if "Series" in str(item.get("type", "")) else "🎬"
            kb.append([InlineKeyboardButton(f"{tp} {item['title']}{yr}"[:60], callback_data=f"m:{i}")])
    markup = InlineKeyboardMarkup(kb)
    await (msg_obj.edit_text(text, reply_markup=markup, parse_mode="HTML") if edit else msg_obj.reply_text(text, reply_markup=markup, parse_mode="HTML"))

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text(f"💡 Usage: <code>/movie Avengers</code>{FOOTER}", parse_mode="HTML"); return
    await do_search(update.message, update.effective_user.id, " ".join(context.args))

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id): return
    await do_search(update.message, update.effective_user.id, update.message.text.strip())

def fmt_stream(s):
    q = s.get("quality") or (f"{s['resolution']}p" if s.get("resolution") else "Stream")
    sz
  
