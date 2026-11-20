import os, json, subprocess, asyncio, re, html, threading, logging, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ["TELEGRAM_TOKEN"]
ADMIN_ID = 7641123461
DB = "users.json"
BRIDGE = os.path.abspath("tg_bridge")
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://moviebox-tg-bot.onrender.com").rstrip("/")
FOOTER = "\n\n⚡ <i>Made by @Dara_OG</i>"
PROVIDERS = [
    ("moviebox", "MovieBox"), ("fourkhdhub", "4KHDHub"), ("dramachi", "Dramachi"),
    ("bdix_circleftp", "CircleFTP"), ("bdix_dhakaflix", "DhakaFlix"), ("addons", "Addons"),
]
SESSIONS = {}
STREAMS_CACHE = {}

class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path == "/" or self.path == "/health":
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK"); return
        parts = self.path.strip("/").split("/")
        if len(parts) < 2 or parts[1] not in STREAMS_CACHE:
            self.send_response(404); self.end_headers(); self.wfile.write(b"Link expired. Search again in Telegram."); return
        action, sid = parts[0], parts[1]
        info = STREAMS_CACHE[sid]
        stream_url = f"{BASE_URL}/s/{sid}"
        if action == "vlc":
            vlc_link = "vlc://" + stream_url
            dl_link = f"{BASE_URL}/dl/{sid}"
            page = f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(info['title'])}</title>
<style>body{{background:#0f172a;color:#fff;font-family:sans-serif;text-align:center;padding:40px 20px}}
.btn{{display:block;max-width:320px;margin:16px auto;padding:16px;border-radius:12px;text-decoration:none;font-weight:bold;font-size:18px}}
.v{{background:#f97316;color:#fff}}.d{{background:#22c55e;color:#fff}}</style></head>
<body><h2>🎬 {html.escape(info['title'])}</h2><p>Quality: {html.escape(info['qual'])}</p>
<a class="btn v" href="{vlc_link}">▶️ Open in VLC</a>
<a class="btn d" href="{dl_link}">⬇️ Download Video</a>
<script>setTimeout(function(){{window.location="{vlc_link}";}},300);</script></body></html>"""
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(page.encode()); return
        if action in ("s", "dl"):
            hdrs = {k: v for k, v in (info.get("headers") or []) if len((k, v)) == 2}
            if "Range" in self.headers: hdrs["Range"] = self.headers["Range"]
            try:
                with httpx.Client(follow_redirects=True, timeout=30.0) as client:
                    with client.stream("GET", info["url"], headers=hdrs) as r:
                        self.send_response(r.status_code)
                        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                            if h in r.headers: self.send_header(h, r.headers[h])
                        if action == "dl":
                            ext = ".mpd" if ".mpd" in info["url"] else ".mp4"
                            self.send_header("Content-Disposition", f'attachment; filename="{info["safe"]}{ext}"')
                        self.end_headers()
                        for chunk in r.iter_bytes(65536):
                            self.wfile.write(chunk)
            except Exception: pass

def start_server():
    port = int(os.environ.get("PORT", "10000"))
    ThreadingHTTPServer(("0.0.0.0", port), ProxyHandler).serve_forever()

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
        await update.message.reply_text(f"🎬 <b>MovieBox Stream Bot Ready!</b>\nSend any movie/series name (e.g. <code>Avatar</code>) or <code>/movie Avengers</code>.{FOOTER}", parse_mode="HTML")
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
    sz = f" • {s['size_mb']}MB" if s.get("size_mb") else ""
    lang = f" • {s['language']}" if s.get("language") else ""
    fmt = " [MPD]" if ".mpd" in s.get("url", "") else " [MP4]"
    return f"🎞 {q}{sz}{lang}{fmt}"[:60]

def quality_kb(streams):
    return InlineKeyboardMarkup([[InlineKeyboardButton(fmt_stream(s), callback_data=f"q:{i}")] for i, s in enumerate(streams[:15])])

async def show_details(q, sess, d):
    seasons = d.get("seasons", [])
    if seasons:
        sess["seasons"] = seasons
        kb = [[InlineKeyboardButton(f"📂 Season {s['number']} ({len(s['episodes'])} eps)", callback_data=f"s:{i}")] for i, s in enumerate(seasons)]
        await q.edit_message_text(f"📺 <b>{esc(d['title'])}</b>\nChoose a season:{FOOTER}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    else:
        streams = d.get("streams", [])
        sess["streams"] = streams
        if not streams:
            await q.edit_message_text(f"❌ <b>No streams found.</b>\nTry another provider.{FOOTER}", parse_mode="HTML"); return
        await q.edit_message_text(f"🎬 <b>{esc(d['title'])}</b>\nSelect stream quality:{FOOTER}", reply_markup=quality_kb(streams), parse_mode="HTML")

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not allowed(uid): await q.answer("Access denied", show_alert=True); return
    await q.answer()
    sess = SESSIONS.get(uid, {})
    data = q.data
    try:
        if data.startswith("p:"):
            prov = data.split(":", 1)[1]
            await q.edit_message_text(f"⚡ Searching on <code>{prov}</code>...{FOOTER}", parse_mode="HTML")
            await do_search(q.message, uid, sess.get("query", ""), prov=prov, edit=True)
        elif data.startswith("m:"):
            item = sess["results"][int(data.split(":")[1])]
            sess["item"] = item
            await q.edit_message_text(f"⏳ Loading <b>{esc(item['title'])}</b>...{FOOTER}", parse_mode="HTML")
            d = await run_bridge("details", item["provider"], item["id"])
            if d.get("error"): await q.edit_message_text(f"❌ {esc(d['error'])}{FOOTER}", parse_mode="HTML"); return
            dubs = d.get("dubs", [])
            if len(dubs) > 1:
                sess["dubs"] = dubs
                kb = [[InlineKeyboardButton(f"🎙 {x.get('label') or x.get('language')}", callback_data=f"dub:{i}")] for i, x in enumerate(dubs)]
                await q.edit_message_text(f"🎙 <b>{esc(d['title'])}</b>\nSelect audio language:{FOOTER}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
            else:
                await show_details(q, sess, d)
        elif data.startswith("dub:"):
            dub = sess["dubs"][int(data.split(":")[1])]
            sess["item"]["id"] = dub["id"]
            lbl = dub.get("label") or dub.get("language")
            await q.edit_message_text(f"⏳ Loading <b>{esc(lbl)}</b>...{FOOTER}", parse_mode="HTML")
            d = await run_bridge("details", sess["item"]["provider"], dub["id"])
            if d.get("error"): await q.edit_message_text(f"❌ {esc(d['error'])}{FOOTER}", parse_mode="HTML"); return
            await show_details(q, sess, d)
        elif data.startswith("s:"):
            season = sess["seasons"][int(data.split(":")[1])]
            sess["season"] = season
            kb, row = [], []
            for i, ep in enumerate(season["episodes"]):
                row.append(InlineKeyboardButton(f"E{ep['number']:02d}", callback_data=f"e:{i}"))
                if len(row) == 4: kb.append(row); row = []
            if row: kb.append(row)
            await q.edit_message_text(f"📺 <b>Season {season['number']}</b>\nPick an episode:{FOOTER}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
        elif data.startswith("e:"):
            ep = sess["season"]["episodes"][int(data.split(":")[1])]
            item = sess["item"]
            await q.edit_message_text(f"⏳ Fetching qualities for <b>S{ep['season']:02d}E{ep['number']:02d}</b>...{FOOTER}", parse_mode="HTML")
            res = await run_bridge("streams", item["provider"], item["id"], str(ep["season"]), str(ep["number"]))
            streams = res.get("streams", [])
            sess["streams"] = streams
            if not streams: await q.edit_message_text(f"❌ No streams found.{FOOTER}", parse_mode="HTML"); return
            await q.edit_message_text(f"📺 <b>{esc(item['title'])}</b> • S{ep['season']:02d}E{ep['number']:02d}\nSelect quality:{FOOTER}", reply_markup=quality_kb(streams), parse_mode="HTML")
        elif data.startswith("q:"):
            idx = int(data.split(":")[1])
            st = sess["streams"][idx]
            qual = st.get("quality") or f"{st.get('resolution', '')}p"
            title = sess["item"]["title"]
            sid = uuid.uuid4().hex[:8]
            safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{title}_{qual}")
            STREAMS_CACHE[sid] = {"url": st["url"], "headers": st.get("headers"), "title": title, "qual": qual, "safe": safe}
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch in VLC", url=f"{BASE_URL}/vlc/{sid}")],
                [InlineKeyboardButton("⬇️ Download", url=f"{BASE_URL}/dl/{sid}")],
                [InlineKeyboardButton("🔗 Copy Stream URL", callback_data=f"url:{idx}")],
            ])
            await q.edit_message_text(f"🎬 <b>{esc(title)}</b>\n🎞 Quality: <b>{esc(qual)}</b>\n\nTap below to play or download:{FOOTER}", reply_markup=kb, parse_mode="HTML")
        elif data.startswith("url:"):
            await q.message.reply_text(sess["streams"][int(data.split(":")[1])]["url"])
    except Exception as e:
        await q.edit_message_text(f"❌ Error: <code>{esc(str(e)[:400])}</code>{FOOTER}", parse_mode="HTML")

threading.Thread(target=start_server, daemon=True).start()
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("allow", allow))
app.add_handler(CommandHandler("remove", remove))
app.add_handler(CommandHandler("users", list_users))
app.add_handler(CommandHandler("movie", movie_search))
app.add_handler(CallbackQueryHandler(on_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.run_polling()
