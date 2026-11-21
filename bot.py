import os, json, subprocess, asyncio, re, html, threading, logging, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ["TELEGRAM_TOKEN"]
ADMIN_ID = 7641123461
DB, FAV_DB, HIST_DB = "users.json", "favs.json", "history.json"
BRIDGE = os.path.abspath("tg_bridge")
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://moviebox-tg-bot.onrender.com").rstrip("/")
HOST = BASE_URL.replace("https://", "").replace("http://", "")
FOOTER = '\n\n⚡ <i>Made by <a href="https://t.me/Dara_OG">@Dara_OG</a></i>'
PROVIDERS = [("moviebox", "Server 1"), ("fourkhdhub", "Server 2"), ("dramachi", "Server 3")]
SESSIONS, STREAMS_CACHE = {}, {}

def jload(p, default): return json.load(open(p)) if os.path.exists(p) else default
def jsave(p, d): json.dump(d, open(p, "w"))
def load_users(): return set(jload(DB, [ADMIN_ID]))
def allowed(uid): return uid == ADMIN_ID or uid in load_users()
def esc(v): return html.escape(str(v or ""))

def filter_results(items, query):
    q_words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
    clean = [x for x in items if not any(b in x.get("title", "").lower() for b in ("xxx", "parody"))]
    if not q_words: return clean[:10]
    exact = [x for x in clean if all(w in x.get("title", "").lower() for w in q_words)]
    pool = exact if exact else clean
    pool.sort(key=lambda x: (0 if x.get("title", "").lower().startswith(query.lower()) else 1, len(x.get("title", ""))))
    return pool[:10]

class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK"); return
        parts = self.path.strip("/").split("/")
        if len(parts) < 2 or parts[1] not in STREAMS_CACHE:
            self.send_response(404); self.end_headers(); self.wfile.write(b"Link expired. Search again in Telegram."); return
        action, sid = parts[0], parts[1]
        info = STREAMS_CACHE[sid]
        stream_url = f"{BASE_URL}/s/{sid}"
        if action == "vlc":
            intent_link = f"intent://{HOST}/s/{sid}#Intent;scheme=https;package=org.videolan.vlc;type=video/*;end"
            vlc_link = f"vlc://{stream_url}"
            dl_link = f"{BASE_URL}/dl/{sid}"
            is_mpd = ".mpd" in info["url"]
            dash_js = '<script src="https://cdn.dashjs.org/latest/dash.all.min.js"></script>' if is_mpd else ""
            dash_init = f'<script>dashjs.MediaPlayer().create().initialize(document.getElementById("v"),"{stream_url}",true);</script>' if is_mpd else ""
            src_attr = "" if is_mpd else f'src="{stream_url}"'
            tracks = "".join(f'<track kind="subtitles" label="{html.escape(c["name"])}" src="{BASE_URL}/sub/{sid}/{i}">' for i, c in enumerate(info.get("captions", [])[:5]))
            meta = f'⭐ {html.escape(info["rating"])} • ' if info.get("rating") else ""
            page = f"""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(info['title'])}</title>{dash_js}
<style>*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at top,#1e1b4b,#090d16 70%);color:#f8fafc;font-family:system-ui,sans-serif;padding:18px;text-align:center}}
.card{{max-width:680px;margin:0 auto;background:rgba(15,23,42,.85);border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:18px;box-shadow:0 20px 50px rgba(0,0,0,.5)}}
.badge{{display:inline-block;background:rgba(249,115,22,.18);color:#fb923c;padding:4px 12px;border-radius:99px;font-size:13px;font-weight:600;margin-bottom:8px}}
video{{width:100%;border-radius:12px;background:#000;margin:10px 0}}
.spd{{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:8px 0 14px}}
.spd button{{background:#1e293b;color:#cbd5e1;border:1px solid #334155;padding:6px 12px;border-radius:8px;font-weight:600;cursor:pointer}}
.btn{{display:block;width:100%;max-width:340px;margin:10px auto;padding:14px;border-radius:12px;text-decoration:none;font-weight:700;font-size:16px}}
.v{{background:linear-gradient(135deg,#f97316,#ea580c);color:#fff}}.v2{{background:#2563eb;color:#fff}}.d{{background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff}}
.ft{{margin-top:16px;font-size:13px;color:#94a3b8}}.ft a{{color:#38bdf8;text-decoration:none;font-weight:600}}</style></head>
<body><div class="card"><div class="badge">{meta}{html.escape(info['qual'])}</div>
<h2 style="margin:4px 0 10px">🎬 {html.escape(info['title'])}</h2>
<video id="v" controls autoplay playsinline crossorigin="anonymous" {src_attr}>{tracks}</video>{dash_init}
<div class="spd"><button onclick="v.playbackRate=0.75">0.75x</button><button onclick="v.playbackRate=1">1x</button><button onclick="v.playbackRate=1.25">1.25x</button><button onclick="v.playbackRate=1.5">1.5x</button><button onclick="v.playbackRate=2">2x</button></div>
<a class="btn v" href="{intent_link}">▶️ Open in VLC App</a>
<a class="btn v2" href="{vlc_link}">🔗 VLC Direct Link</a>
<a class="btn d" href="{dl_link}">⬇️ Download Video</a>
<p style="font-size:12px;color:#64748b">Tip: Inside Telegram, tap ⋮ → Open in Chrome for VLC App</p>
<div class="ft"><a href="https://t.me/Dara_OG">⚡ Made by @Dara_OG</a></div></div></body></html>"""
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(page.encode()); return
        if action == "sub" and len(parts) >= 3:
            idx = int(parts[2])
            caps = info.get("captions", [])
            if idx < len(caps):
                try:
                    r = httpx.get(caps[idx]["url"], follow_redirects=True, timeout=15.0)
                    txt = r.text
                    if not txt.lstrip().startswith("WEBVTT"):
                        txt = "WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", txt)
                    self.send_response(200); self.send_header("Content-Type", "text/vtt; charset=utf-8"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
                    self.wfile.write(txt.encode()); return
                except Exception: pass
            self.send_response(404); self.end_headers(); return
        if action in ("s", "dl"):
            hdrs = {k: v for k, v in (info.get("headers") or []) if len((k, v)) == 2}
            if "Range" in self.headers: hdrs["Range"] = self.headers["Range"]
            try:
                with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(15.0, read=None, write=60.0)) as client:
                    with client.stream("GET", info["url"], headers=hdrs) as r:
                        self.send_response(r.status_code)
                        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                            if h in r.headers: self.send_header(h, r.headers[h])
                        if action == "dl":
                            ext = ".mpd" if ".mpd" in info["url"] else ".mp4"
                            self.send_header("Content-Disposition", f'attachment; filename="{info["safe"]}{ext}"')
                        self.end_headers()
                        for chunk in r.iter_bytes(65536): self.wfile.write(chunk)
            except Exception: pass

def start_server():
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), ProxyHandler).serve_forever()

async def safe_edit(q, text, markup=None, force_text=False):
    if q.message.photo and force_text:
        await q.message.delete()
        await q.message.reply_text(text[:4090], reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    elif q.message.photo:
        await q.edit_message_caption(caption=text[:1020], reply_markup=markup, parse_mode="HTML")
    else:
        await q.edit_message_text(text=text[:4090], reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

async def run_bridge(*args):
    res = await asyncio.to_thread(subprocess.run, [BRIDGE, *args], capture_output=True, text=True, timeout=90)
    return {"error": res.stderr[:800] or "Bridge error"} if res.returncode != 0 else json.loads(res.stdout)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if allowed(uid):
        await update.message.reply_text(f"🎬 <b>MovieBox Pro Bot</b>\n• Send any movie/series name\n• <code>/trending</code> — Latest hits\n• <code>/fav</code> — Saved watchlist\n• <code>/history</code> — Continue watching{FOOTER}", parse_mode="HTML", disable_web_page_preview=True)
    else:
        await update.message.reply_text(f"🔒 <b>Access Denied</b>\nSend ID to Admin: <code>{uid}</code>{FOOTER}", parse_mode="HTML", disable_web_page_preview=True)

async def allow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.args: return
    u = load_users(); u.add(int(context.args[0])); jsave(DB, list(u))
    await update.message.reply_text(f"✅ Allowed: {context.args[0]}")

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or not context.args: return
    u = load_users(); u.discard(int(context.args[0])); jsave(DB, list(u))
    await update.message.reply_text(f"🗑 Removed: {context.args[0]}")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("👥 Allowed IDs: " + ", ".join(map(str, sorted(load_users()))))

def results_kb(results, prov=None):
    kb = []
    if prov:
        kb.append([InlineKeyboardButton(f"{'✅ ' if k == prov else ''}{lbl}", callback_data=f"p:{k}") for k, lbl in PROVIDERS])
    for i, item in enumerate(results):
        yr = f" ({item['year']})" if item.get("year") else ""
        tp = "📺" if "Series" in str(item.get("type", "")) else "🎬"
        kb.append([InlineKeyboardButton(f"{tp} {item['title']}{yr}"[:60], callback_data=f"m:{i}")])
    return InlineKeyboardMarkup(kb)

async def do_search(msg_obj, uid, query, prov="moviebox", edit=False):
    SESSIONS[uid] = {"query": query, "prov": prov}
    data = await run_bridge("search", prov, query)
    results = filter_results(data.get("results", []), query)
    SESSIONS[uid]["results"] = results
    lbl = dict(PROVIDERS).get(prov, prov)
    if data.get("error"): text = f"🔎 <b>{esc(query)}</b> • <code>{lbl}</code>\n❌ {esc(data['error'])}{FOOTER}"
    elif not results: text = f"🔎 <b>{esc(query)}</b> • <code>{lbl}</code>\n😕 No exact match found. Try another server:{FOOTER}"
    else: text = f"🍿 <b>Search Results</b> • <code>{lbl}</code>\n🔎 <i>{esc(query)}</i>\n\nPick a title below:{FOOTER}"
    markup = results_kb(results, prov)
    await (msg_obj.edit_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True) if edit else msg_obj.reply_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True))

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not allowed(uid): return
    data = await run_bridge("trending")
    results = data.get("results", [])
    SESSIONS[uid] = {"query": "Trending", "prov": "moviebox", "results": results}
    if not results: await update.message.reply_text(f"❌ Could not load trending.{FOOTER}", parse_mode="HTML"); return
    await update.message.reply_text(f"🔥 <b>Trending Now</b>\nPick a title:{FOOTER}", reply_markup=results_kb(results), parse_mode="HTML", disable_web_page_preview=True)

async def fav_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not allowed(uid): return
    favs = jload(FAV_DB, {}).get(str(uid), [])
    if not favs: await update.message.reply_text(f"⭐ <b>Watchlist empty.</b>\nOpen any movie and tap ⭐ Save!{FOOTER}", parse_mode="HTML", disable_web_page_preview=True); return
    SESSIONS[uid] = {"query": "Favorites", "prov": "moviebox", "results": favs}
    await update.message.reply_text(f"⭐ <b>Your Watchlist</b>{FOOTER}", reply_markup=results_kb(favs), parse_mode="HTML", disable_web_page_preview=True)

async def hist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not allowed(uid): return
    hist = jload(HIST_DB, {}).get(str(uid), [])
    if not hist: await update.message.reply_text(f"🕒 <b>No watch history yet.</b>{FOOTER}", parse_mode="HTML", disable_web_page_preview=True); return
    SESSIONS[uid] = {"query": "History", "prov": "moviebox", "results": hist}
    await update.message.reply_text(f"🕒 <b>Continue Watching</b>{FOOTER}", reply_markup=results_kb(hist), parse_mode="HTML", disable_web_page_preview=True)

async def movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id): return
    if not context.args: await update.message.reply_text(f"💡 Usage: <code>/movie Avengers</code>{FOOTER}", parse_mode="HTML"); return
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

def quality_kb(streams, back="back:res"):
    kb = [[InlineKeyboardButton(fmt_stream(s), callback_data=f"q:{i}")] for i, s in enumerate(streams[:15])]
    kb.append([InlineKeyboardButton("⭐ Save", callback_data="save"), InlineKeyboardButton("⬅️ Back", callback_data=back)])
    return InlineKeyboardMarkup(kb)

def info_header(d):
    parts = [f"🎬 <b>{esc(d.get('title'))}</b>"]
    meta = [x for x in (d.get("year"), f"⭐ {d['rating']}" if d.get("rating") else None, d.get("duration")) if x]
    if meta: parts.append(" • ".join(map(esc, meta)))
    if d.get("plot"): parts.append(f"<i>{esc(d['plot'][:200])}...</i>")
    return "\n".join(parts)

async def show_details(q, sess, d):
    sess["details"] = d
    hdr = info_header(d)
    seasons = d.get("seasons", [])
    if seasons:
        sess["seasons"] = seasons
        kb = [[InlineKeyboardButton(f"📂 Season {s['number']} ({len(s['episodes'])} eps)", callback_data=f"s:{i}")] for i, s in enumerate(seasons)]
        kb.append([InlineKeyboardButton("⭐ Save", callback_data="save"), InlineKeyboardButton("⬅️ Back", callback_data="back:res")])
        await safe_edit(q, f"{hdr}\n\nChoose a season:{FOOTER}", InlineKeyboardMarkup(kb))
    else:
        streams = d.get("streams", [])
        sess["streams"], sess["captions"] = streams, d.get("captions", [])
        if not streams:
            await safe_edit(q, f"{hdr}\n\n❌ <b>No streams found.</b> Try another server.{FOOTER}", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back:res")]])); return
        await safe_edit(q, f"{hdr}\n\nSelect stream quality:{FOOTER}", quality_kb(streams))

def save_history(uid, item):
    all_h = jload(HIST_DB, {})
    h = [x for x in all_h.get(str(uid), []) if x.get("id") != item.get("id")]
    h.insert(0, item)
    all_h[str(uid)] = h[:10]
    jsave(HIST_DB, all_h)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not allowed(uid): await q.answer("Access denied", show_alert=True); return
    sess = SESSIONS.get(uid, {})
    data = q.data
    if data == "save":
        item = sess.get("item")
        if item:
            all_f = jload(FAV_DB, {})
            f = [x for x in all_f.get(str(uid), []) if x.get("id") != item.get("id")]
            f.insert(0, item); all_f[str(uid)] = f[:20]; jsave(FAV_DB, all_f)
        await q.answer("⭐ Saved to /fav!", show_alert=True); return
    await q.answer()
    try:
        if data.startswith("p:"):
            prov = data.split(":", 1)[1]
            await safe_edit(q, f"⚡ Searching on <code>{dict(PROVIDERS).get(prov, prov)}</code>...{FOOTER}", force_text=True)
            await do_search(q.message, uid, sess.get("query", ""), prov=prov, edit=True)
        elif data.startswith("m:"):
            item = sess["results"][int(data.split(":")[1])]
            sess["item"] = item
            await safe_edit(q, f"⏳ Loading <b>{esc(item['title'])}</b>...{FOOTER}")
            d = await run_bridge("details", item["provider"], item["id"])
            if d.get("error"): await safe_edit(q, f"❌ {esc(d['error'])}{FOOTER}"); return
            if d.get("poster") and not q.message.photo:
                try:
                    m = await q.message.reply_photo(photo=d["poster"], caption=f"⏳ Loading <b>{esc(d['title'])}</b>...{FOOTER}", parse_mode="HTML")
                    await q.message.delete()
                    q = type("Q", (), {"message": m, "edit_message_caption": m.edit_caption, "edit_message_text": m.edit_text})()
                except Exception: pass
            dubs = d.get("dubs", [])
            if len(dubs) > 1:
                sess["dubs"] = dubs
                kb = [[InlineKeyboardButton(f"🎙 {x.get('label') or x.get('language')}", callback_data=f"dub:{i}")] for i, x in enumerate(dubs)]
                kb.append([InlineKeyboardButton("⬅️ Back", callback_data="back:res")])
                await safe_edit(q, f"{info_header(d)}\n\nSelect audio language:{FOOTER}", InlineKeyboardMarkup(kb))
            else:
                await show_details(q, sess, d)
        elif data.startswith("dub:"):
            dub = sess["dubs"][int(data.split(":")[1])]
            sess["item"]["id"] = dub["id"]
            await safe_edit(q, f"⏳ Loading <b>{esc(dub.get('label') or dub.get('language'))}</b>...{FOOTER}")
            d = await run_bridge("details", sess["item"]["provider"], dub["id"])
            if d.get("error"): await safe_edit(q, f"❌ {esc(d['error'])}{FOOTER}"); return
            await show_details(q, sess, d)
        elif data.startswith("s:"):
            season = sess["seasons"][int(data.split(":")[1])]
            sess["season"] = season
            kb, row = [], []
            for i, ep in enumerate(season["episodes"]):
                row.append(InlineKeyboardButton(f"E{ep['number']:02d}", callback_data=f"e:{i}"))
                if len(row) == 4: kb.append(row); row = []
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("⬅️ Back", callback_data="back:seasons")])
            await safe_edit(q, f"📺 <b>Season {season['number']}</b>\nPick an episode:{FOOTER}", InlineKeyboardMarkup(kb))
        elif data.startswith("e:"):
            e_idx = int(data.split(":")[1])
            sess["e_idx"] = e_idx
            ep = sess["season"]["episodes"][e_idx]
            item = sess["item"]
            await safe_edit(q, f"⏳ Fetching <b>S{ep['season']:02d}E{ep['number']:02d}</b>...{FOOTER}")
            res = await run_bridge("streams", item["provider"], item["id"], str(ep["season"]), str(ep["number"]))
            streams = res.get("streams", [])
            sess["streams"], sess["captions"] = streams, res.get("captions", [])
            if not streams: await safe_edit(q, f"❌ No streams found.{FOOTER}", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back:eps")]])); return
            await safe_edit(q, f"📺 <b>{esc(item['title'])}</b> • S{ep['season']:02d}E{ep['number']:02d}\nSelect quality:{FOOTE
