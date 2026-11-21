import os, json, subprocess, asyncio, re, html, threading, logging, uuid
from urllib.parse import urljoin, quote
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
PROVIDERS = [
    ("moviebox", "Server 1"), ("fourkhdhub", "Server 2"), ("dramachi", "Server 3"),
    ("bdix_circleftp", "Server 4"), ("bdix_dhakaflix", "Server 5"), ("addons", "Server 6"),
]
SESSIONS, STREAMS_CACHE = {}, {}
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

def jload(p, d): return json.load(open(p)) if os.path.exists(p) else d
def jsave(p, d): json.dump(d, open(p, "w"))
def load_users(): return set(jload(DB, [ADMIN_ID]))
def allowed(uid): return uid == ADMIN_ID or uid in load_users()
def esc(v): return html.escape(str(v or ""))

def parse_headers(raw_hdrs):
    hdrs = {"User-Agent": DEFAULT_UA}
    if isinstance(raw_hdrs, dict):
        hdrs.update({str(k): str(v) for k, v in raw_hdrs.items() if v})
    elif isinstance(raw_hdrs, list):
        for item in raw_hdrs:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                hdrs[str(item[0])] = str(item[1])
    return hdrs

def filter_results(items, query):
    qw = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
    clean = [x for x in items if not any(b in x.get("title", "").lower() for b in ("xxx", "parody"))]
    if not qw: return clean[:10]
    exact = [x for x in clean if all(w in x.get("title", "").lower() for w in qw)]
    pool = exact if exact else clean
    pool.sort(key=lambda x: (0 if x.get("title", "").lower().startswith(query.lower()) else 1, len(x.get("title", ""))))
    return pool[:10]
    class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_HEAD(self): self.send_response(200); self.end_headers()
    def do_GET(self):
        if self.path in ("/", "/health"):
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK"); return
        clean_path = self.path.split("?", 1)[0]
        parts = clean_path.strip("/").split("/")
        if len(parts) < 2 or parts[1] not in STREAMS_CACHE:
            self.send_response(404); self.end_headers(); self.wfile.write(b"Link expired. Search again."); return
        act, sid = parts[0], parts[1]
        info = STREAMS_CACHE[sid]
        surl = f"{BASE_URL}/s/{sid}"
        hdrs = parse_headers(info.get("headers"))
        raw_url = info["url"]
        lower_url = raw_url.split("?")[0].lower()

        if act == "vlc":
            ilink = f"intent://{HOST}/s/{sid}#Intent;scheme=https;package=org.videolan.vlc;type=video/*;end"
            is_mpd = ".mpd" in lower_url
            is_m3u8 = ".m3u8" in lower_url
            is_mkv = ".mkv" in lower_url

            player_js = ""
            if is_mpd:
                player_js = f'<script src="https://cdn.dashjs.org/latest/dash.all.min.js"></script><script>dashjs.MediaPlayer().create().initialize(document.getElementById("v"),"{surl}",true);</script>'
            elif is_m3u8:
                player_js = (
                    '<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>'
                    f'<script>const v=document.getElementById("v");if(Hls.isSupported()){{const h=new Hls();h.loadSource("{surl}");h.attachMedia(v);}}else if(v.canPlayType("application/vnd.apple.mpegurl")){{v.src="{surl}";}}</script>'
                )

            src = "" if (is_mpd or is_m3u8) else f'src="{surl}"'
            mkv_note = '<div style="background:#7c2d12;color:#fed7aa;padding:8px;border-radius:10px;font-size:13px;margin:6px 0">⚠️ MKV format browser me play nahi hota. Neeche <b>Open in VLC App</b> ya <b>Download Video</b> use karein.</div>' if is_mkv else ""
            trks = "".join(f'<track kind="subtitles" label="{esc(c["name"])}" src="{BASE_URL}/sub/{sid}/{i}">' for i, c in enumerate(info.get("captions", [])[:5]))
            meta = f'⭐ {esc(info["rating"])} • ' if info.get("rating") else ""
            page = (
                f'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{esc(info["title"])}</title>'
                f'<style>*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:radial-gradient(circle at top,#1e1b4b,#090d16 70%);color:#f8fafc;font-family:system-ui,sans-serif;padding:14px;text-align:center}}'
                f'.card{{max-width:680px;margin:0 auto;background:rgba(15,23,42,.88);border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:16px}}'
                f'.badge{{display:inline-block;background:rgba(249,115,22,.18);color:#fb923c;padding:4px 12px;border-radius:99px;font-size:13px;font-weight:600;margin-bottom:6px}}'
                f'video{{width:100%;border-radius:12px;background:#000;margin:8px 0}}'
                f'.row{{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:8px 0;align-items:center}}'
                f'.row button{{background:#1e293b;color:#e2e8f0;border:1px solid #334155;padding:7px 11px;border-radius:8px;font-weight:600;cursor:pointer}}'
                f'.sliders{{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:10px;margin:10px 0;text-align:left;font-size:13px}}'
                f'.sliders label{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:6px 0}}.sliders input{{flex:1;accent-color:#f97316}}'
                f'.btn{{display:block;width:100%;max-width:340px;margin:9px auto;padding:13px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px}}'
                f'.v{{background:#f97316;color:#fff}}.v2{{background:#2563eb;color:#fff}}.d{{background:#16a34a;color:#fff}}'
                f'#lk{{display:none;position:fixed;inset:0;z-index:9999;background:transparent}}'
                f'#ulk{{position:fixed;top:16px;right:16px;background:rgba(15,23,42,.9);color:#fff;border:1px solid #475569;padding:10px 14px;border-radius:99px;font-weight:700}}'
                f'.ft{{margin-top:14px;font-size:13px}}.ft a{{color:#38bdf8;text-decoration:none;font-weight:600}}</style></head>'
                f'<body><div id="lk"><button id="ulk" onclick="lk.style.display=\'none\'">🔓 Unlock</button></div>'
                f'<div class="card"><div class="badge">{meta}{esc(info["qual"])}</div>'
                f'<h2 style="margin:4px 0 8px">🎬 {esc(info["title"])}</h2>{mkv_note}'
                f'<video id="v" controls autoplay playsinline crossorigin="anonymous" {src}>{trks}</video>{player_js}'
                f'<div class="row"><button onclick="v.currentTime-=10">⏪ 10s</button><button onclick="v.currentTime+=10">⏩ 10s</button><button onclick="lk.style.display=\'block\'">🔒 Lock</button></div>'
                f'<div class="row"><button onclick="v.playbackRate=0.75">0.75x</button><button onclick="v.playbackRate=1">1x</button><button onclick="v.playbackRate=1.25">1.25x</button><button onclick="v.playbackRate=1.5">1.5x</button><button onclick="v.playbackRate=2">2x</button></div>'
                f'<div class="sliders"><label>☀️ Brightness <input type="range" min="0.3" max="1.6" step="0.05" value="1" oninput="v.style.filter=\'brightness(\'+this.value+\')\'" ></label>'
                f'<label>🔊 Volume <input type="range" min="0" max="1" step="0.05" value="1" oninput="v.volume=this.value"></label></div>'
                f'<a class="btn v" href="{ilink}">▶️ Open in VLC App</a>'
                f'<a class="btn v2" href="vlc://{HOST}/s/{sid}">🔗 VLC Direct Link</a>'
                f'<a class="btn d" href="{BASE_URL}/dl/{sid}" target="_blank">⬇️ Download Video</a>'
                f'<div class="ft"><a href="https://t.me/Dara_OG">⚡ Made by @Dara_OG</a></div></div></body></html>'
            )
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(page.encode()); return

        if act == "sub" and len(parts) >= 3:
            idx = int(parts[2]); caps = info.get("captions", [])
            if idx < len(caps):
                try:
                    txt = httpx.get(caps[idx]["url"], headers=hdrs, follow_redirects=True, timeout=15.0).text
                    if not txt.lstrip().startswith("WEBVTT"): txt = "WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", txt)
                    self.send_response(200); self.send_header("Content-Type", "text/vtt; charset=utf-8"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
                    self.wfile.write(txt.encode()); return
                except Exception: pass
            self.send_response(404); self.end_headers(); return

        if act == "s" and ".mpd" in lower_url:
            try:
                xml = httpx.get(raw_url, headers=hdrs, follow_redirects=True, timeout=15.0).text
                base = f"{BASE_URL}/seg/{sid}/"
                xml = re.sub(r"<BaseURL>[^<]*</BaseURL>", "", xml)
                xml = re.sub(r"(<MPD[^>]*>)", rf"\1<BaseURL>{base}</BaseURL>", xml, count=1)
                self.send_response(200); self.send_header("Content-Type", "application/dash+xml"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
                self.wfile.write(xml.encode()); return
            except Exception:
                self.send_response(502); self.end_headers(); return

        if act in ("s", "hls") and (".m3u8" in lower_url or act == "hls"):
            target_m3u8 = raw_url
            if act == "hls" and "u=" in self.path:
                from urllib.parse import unquote
                target_m3u8 = unquote(self.path.split("u=", 1)[1])
            try:
                r = httpx.get(target_m3u8, headers=hdrs, follow_redirects=True, timeout=15.0)
                final_base = str(r.url)
                lines = []
                for line in r.text.splitlines():
                    sline = line.strip()
                    if not sline or sline.startswith("#"):
                        if 'URI="' in sline:
                            def repl_uri(m):
                                abs_u = urljoin(final_base, m.group(1))
                                route = "hls" if ".m3u8" in abs_u.lower() else "seg_u"
                                return f'URI="{BASE_URL}/{route}/{sid}?u={quote(abs_u, safe="")}"'
                            sline = re.sub(r'URI="([^"]+)"', repl_uri, sline)
                        lines.append(sline)
                    else:
                        abs_u = urljoin(final_base, sline)
                        route = "hls" if ".m3u8" in abs_u.lower() else "seg_u"
                        lines.append(f"{BASE_URL}/{route}/{sid}?u={quote(abs_u, safe='')}")
                body = "\n".join(lines).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return
            except Exception as e:
                logging.error(f"M3U8 proxy error: {e}")
                self.send_response(502); self.end_headers(); return

        if act in ("s", "dl", "seg", "seg_u"):
            target = raw_url
            if act == "seg":
                sub = "/".join(parts[2:])
                if "?" in self.path: sub += "?" + self.path.split("?", 1)[1]
                target = urljoin(raw_url, sub)
            elif act == "seg_u" and "u=" in self.path:
                from urllib.parse import unquote
                target = unquote(self.path.split("u=", 1)[1])

            if "Range" in self.headers: hdrs["Range"] = self.headers["Range"]
            try:
                with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(20.0, read=None, write=60.0)) as client:
                    with client.stream("GET", target, headers=hdrs) as r:
                        self.send_response(r.status_code)
                        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                            if h in r.headers: self.send_header(h, r.headers[h])
                        self.send_header("Access-Control-Allow-Origin", "*")
                        if act == "dl":
                            ext = ".mkv" if ".mkv" in lower_url else (".mpd" if ".mpd" in lower_url else (".m3u8" if ".m3u8" in lower_url else ".mp4"))
                            self.send_header("Content-Disposition", f'attachment; filename="{info["safe"]}{ext}"')
                        self.end_headers()
                        for chunk in r.iter_bytes(65536): self.wfile.write(chunk)
            except Exception as e:
                logging.error(f"Stream error ({target}): {e}")
                def start_server(): ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), ProxyHandler).serve_forever()
async def safe_edit(q, text, markup=None, force_text=False):
    if q.message.photo and force_text:
        await q.message.delete()
        await q.message.reply_text(text[:4090], reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    elif q.message.photo: await q.edit_message_caption(caption=text[:1020], reply_markup=markup, parse_mode="HTML")
    else: await q.edit_message_text(text=text[:4090], reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

async def run_bridge(*args):
    res = await asyncio.to_thread(subprocess.run, [BRIDGE, *args], capture_output=True, text=True, timeout=90)
    return {"error": res.stderr[:800] or "Bridge error"} if res.returncode != 0 else json.loads(res.stdout)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        await update.message.reply_text(f"👑 <b>Admin Mode Ready</b>\n• Send movie/series name\n• <code>/trending</code> | <code>/fav</code> | <code>/history</code>\n\n<b>Admin:</b>\n• <code>/allow &lt;id&gt;</code>\n• <code>/remove &lt;id&gt;</code>\n• <code>/users</code>{FOOTER}", parse_mode="HTML", disable_web_page_preview=True)
    elif allowed(uid):
        await update.message.reply_text(f"🎬 <b>MovieBox Pro Bot</b>\n• Send any movie/series name\n• <code>/trending</code> | <code>/fav</code> | <code>/history</code>{FOOTER}", parse_mode="HTML", disable_web_page_preview=True)
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
        kb.append([InlineKeyboardButton(f"{'✅ ' if k == prov else ''}{lbl}", callback_data=f"p:{k}") for k, lbl in PROVIDERS[:3]])
        kb.append([InlineKeyboardButton(f"{'✅ ' if k == prov else ''}{lbl}", callback_data=f"p:{k}") for k, lbl in PROVIDERS[3:]])
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
    elif not results: text = f"🔎 <b>{esc(query)}</b> • <code>{lbl}</code>\n😕 No exact match. Try another server:{FOOTER}"
    else: text = f"🍿 <b>Search Results</b> • <code>{lbl}</code>\n🔎 <i>{esc(query)}</i>\n\nPick a title below:{FOOTER}"
    markup = results_kb(results, prov)
    await (msg_obj.edit_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True) if edit else msg_obj.reply_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True))

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not allowed(uid): return
    results = (await run_bridge("trending")).get("results", [])
    SESSIONS[uid] = {"query": "Trending", "prov": "moviebox", "results": results}
    if not results: await update.message.reply_text(f"❌ Could not load trending.{FOOTER}", parse_mode="HTML"); return
    await update.message.reply_text(f"🔥 <b>Trending Now</b>{FOOTER}", reply_markup=results_kb(results), parse_mode="HTML", disable_web_page_preview=True)

async def fav_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not allowed(uid): return
    favs = jload(FAV_DB, {}).get(str(uid), [])
    if not favs: await update.message.reply_text(f"⭐ <b>Watchlist empty.</b>{FOOTER}", parse_mode="HTML", disable_web_page_preview=True); return
    SESSIONS[uid] = {"query": "Favorites", "prov": "moviebox", "results": favs}
    await update.message.reply_text(f"⭐ <b>Your Watchlist</b>{FOOTER}", reply_markup=results_kb(favs), parse_mode="HTML", disable_web_page_preview=True)

async def hist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not allowed(uid): return
    hist = jload(HIST_DB, {}).get(str(uid), [])
    if not hist: await update.message.reply_text(f"🕒 <b>No history yet.</b>{FOOTER}", parse_mode="HTML", disable_web_page_preview=True); return
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
    u = s.get("url", "").lower()
    fmt = " [MPD]" if ".mpd" in u else (" [HLS]" if ".m3u8" in u else (" [MKV]" if ".mkv" in u else " [MP4]"))
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
    sess["details"] = d; hdr = info_header(d); seasons = d.get("seasons", [])
    if seasons:
        sess["seasons"] = seasons
        kb = [[InlineKeyboardButton(f"📂 Season {s['number']} ({len(s['episodes'])} eps)", callback_data=f"s:{i}")] for i, s in enumerate(seasons)]
        kb.append([InlineKeyboardButton("⭐ Save", callback_data="save"), InlineKeyboardButton("⬅️ Back", callback_data="back:res")])
        await safe_edit(q, f"{hdr}\n\nChoose a season:{FOOTER}", InlineKeyboardMarkup(kb))
    else:
        streams = d.get("streams", [])
        sess["streams"], sess["captions"] = streams, d.get("captions", [])
        if not streams:
            await safe_edit(q, f"{hdr}\n\n❌ <b>No streams found.</b>{FOOTER}", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back:res")]])); return
        await safe_edit(q, f"{hdr}\n\nSelect stream quality:{FOOTER}", quality_kb(streams))

def save_history(uid, item):
    all_h = jload(HIST_DB, {})
    h = [x for x in all_h.get(str(uid), []) if x.get("id") != item.get("id")]
    h.insert(0, item); all_h[str(uid)] = h[:10]; jsave(HIST_DB, all_h)

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; uid = q.from_user.id
    if not allowed(uid): await q.answer("Access denied", show_alert=True); return
    sess = SESSIONS.get(uid, {}); data = q.data
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
            item = sess["results"][int(data.split(":")[1])]; sess["item"] = item
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
            else: await show_details(q, sess, d)
        elif data.startswith("dub:"):
            dub = sess["dubs"][int(data.split(":")[1])]; sess["item"]["id"] = dub["id"]
            await safe_edit(q, f"⏳ Loading <b>{esc(dub.get('label') or dub.get('language'))}</b>...{FOOTER}")
            d = await run_bridge("details", sess["item"]["provider"], dub["id"])
            if d.get("error"): await safe_edit(q, f"❌ {esc(d['error'])}{FOOTER}"); return
            await show_details(q, sess, d)
        elif data.startswith("s:"):
            season = sess["seasons"][int(data.split(":")[1])]; sess["season"] = season; kb, row = [], []
            for i, ep in enumerate(season["episodes"]):
                row.append(InlineKeyboardButton(f"E{ep['number']:02d}", callback_data=f"e:{i}"))
                if len(row) == 4: kb.append(row); row = []
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("⬅️ Back", callback_data="back:seasons")])
            await safe_edit(q, f"📺 <b>Season {season['number']}</b>\nPick an episode:{FOOTER}", InlineKeyboardMarkup(kb))
        elif data.startswith("e:"):
            e_idx = int(data.split(":")[1]); sess["e_idx"] = e_idx
            ep = sess["season"]["episodes"][e_idx]; item = sess["item"]
            await safe_edit(q, f"⏳ Fetching <b>S{ep['season']:02d}E{ep['number']:02d}</b>...{FOOTER}")
            res = await run_bridge("streams", item["provider"], item["id"], str(ep["season"]), str(ep["number"]))
            streams = res.get("streams", [])
            sess["streams"], sess["captions"] = streams, res.get("captions", [])
            if not streams: await safe_edit(q, f"❌ No streams found.{FOOTER}", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back:eps")]])); return
            await safe_edit(q, f"📺 <b>{esc(item['title'])}</b> • S{ep['season']:02d}E{ep['number']:02d}\nSelect quality:{FOOTER}", quality_kb(streams, "back:eps"))
        elif data.startswith("q:"):
            idx = int(data.split(":")[1]); st = sess["streams"][idx]
            qual = st.get("quality") or f"{st.get('resolution', '')}p"; title = sess["item"]["title"]
            save_history(uid, sess["item"]); sid = uuid.uuid4().hex[:8]
            safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{title}_{qual}")
            d = sess.get("details", {})
            STREAMS_CACHE[sid] = {"url": st["url"], "headers": st.get("headers"), "title": title, "qual": qual, "safe": safe, "rating": d.get("rating"), "captions": sess.get("captions", [])}
            kb = [[InlineKeyboardButton("▶️ Watch / Open in VLC", url=f"{BASE_URL}/vlc/{sid}")], [InlineKeyboardButton("⬇️ Download", url=f"{BASE_URL}/dl/{sid}")]]
            if sess.get("season") and sess.get("e_idx", -1) + 1 < len(sess["season"]["episodes"]):
                kb.append([InlineKeyboardButton("⏭ Next Episode", callback_data=f"e:{sess['e_idx']+1}")])
            kb.append([InlineKeyboardButton("🔗 Copy URL", callback_data=f"url:{idx}"), InlineKeyboardButton("⬅️ Back", callback_data="back:q")])
            await safe_edit(q, f"🎬 <b>{esc(title)}</b>\n🎞 Quality: <b>{esc(qual)}</b>\n\nTap below to play or download:{FOOTER}", InlineKeyboardMarkup(kb))
        elif data == "back:res":
            await safe_edit(q, f"🍿 <b>{esc(sess.get('query', 'Results'))}</b>\nPick a title:{FOOTER}", results_kb(sess.get("results", []), sess.get("prov")), force_text=True)
        elif data == "back:seasons": await show_details(q, sess, sess["details"])
        elif data == "back:eps":
            season = sess["season"]; kb, row = [], []
            for i, ep in enumerate(season["episodes"]):
                row.append(InlineKeyboardButton(f"E{ep['number']:02d}", callback_data=f"e:{i}"))
                if len(row) == 4: kb.append(row); row = []
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("⬅️ Back", callback_data="back:seasons")])
            await safe_edit(q, f"📺 <b>Season {season['number']}</b>\nPick an episode:{FOOTER}", InlineKeyboardMarkup(kb))
        elif data == "back:q":
            await safe_edit(q, f"🎬 <b>{esc(sess['item']['title'])}</b>\nSelect stream quality:{FOOTER}", quality_kb(sess.get("streams", []), "back:eps" if sess.get("season") else "back:res"))
        elif data.startswith("url:"): await q.message.reply_text(sess["streams"][int(data.split(":")[1])]["url"])
    except Exception as e:
        await safe_edit(q, f"❌ Error: <code>{esc(str(e)[:400])}</code>{FOOTER}")

threading.Thread(target=start_server, daemon=True).start()
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("trending", trending_cmd))
app.add_handler(CommandHandler("fav", fav_cmd))
app.add_handler(CommandHandler("history", hist_cmd))
app.add_handler(CommandHandler("allow", allow))
app.add_handler(CommandHandler("remove", remove))
app.add_handler(CommandHandler("users", list_users))
app.add_handler(CommandHandler("movie", movie_search))
app.add_handler(CallbackQueryHandler(on_callback))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.run_polling()
                
