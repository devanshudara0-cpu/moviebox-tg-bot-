import os, json, subprocess, asyncio, re, html, threading, logging, uuid, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from media_resolver import AsyncMediaClient, SessionStore
from provider_adapters import AdapterRegistry
import sites_scraper
import app_portal

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ADMIN_ID = 7641123461
DB, FAV_DB, HIST_DB = "users.json", "favs.json", "history.json"
BRIDGE = os.path.abspath("tg_bridge")
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://leo-final-boss.onrender.com").rstrip("/")
HOST = BASE_URL.replace("https://", "").replace("http://", "")
FOOTER = '\n\n⚡ <i>Made by <a href="https://t.me/Dara_OG">@Dara_OG</a></i>'
PROVIDERS = [
    ("ottstream", "Server 1"),
    ("moviebox", "Server 2"),
    ("fourkhdhub", "Server 3"),
    ("vegamovies", "Server 4"),
    ("katmovieshd", "Server 5"),
    ("rogmovies", "Server 6"),
]
SESSIONS, STREAMS_CACHE = {}, {}
MEDIA_SESSIONS = SessionStore()
MEDIA_CLIENT = AsyncMediaClient(timeout=15.0, max_retries=2, max_redirects=5)
SERVER2_ADAPTERS = AdapterRegistry()
HTTP_POOL = httpx.Client(follow_redirects=True, timeout=httpx.Timeout(15.0, read=None, write=60.0), limits=httpx.Limits(max_connections=30, max_keepalive_connections=15))

def jload(p, d): return json.load(open(p)) if os.path.exists(p) else d
def jsave(p, d): json.dump(d, open(p, "w"))
def load_users(): return set(jload(DB, [ADMIN_ID]))
def allowed(uid): return uid == ADMIN_ID or uid in load_users()
def esc(v): return html.escape(str(v or ""))

def filter_results(items, query):
    if not items:
        return []
    qw = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
    clean = [x for x in items if not any(b in x.get("title", "").lower() for b in ("xxx", "parody"))]
    if not qw:
        return clean[:15]
    scored = []
    q_low = query.lower().strip()
    for x in clean:
        t_low = x.get("title", "").lower()
        score = 0
        if t_low.startswith(q_low):
            score += 100
        elif q_low in t_low:
            score += 50
        matches = sum(1 for w in qw if w in t_low)
        score += matches * 10
        if matches > 0 or score > 0:
            scored.append((score, x))
    scored.sort(key=lambda s: s[0], reverse=True)
    res = [x for _, x in scored]
    return res[:15] if res else clean[:15]

async def resolve_server2_streams(uid: int, raw_streams: list, client: AsyncMediaClient = None):
    """Preserve MovieBox-Tui bridge streams and headers for HDHub, ensuring direct VLC playback."""
    resolved, seen_urls = [], set()
    for st in raw_streams or []:
        raw_url = (st.get("url") or "").strip()
        if not raw_url or raw_url in seen_urls:
            continue
        seen_urls.add(raw_url)
        resolved.append(st)
    resolved.sort(key=lambda x: int(x.get("resolution") or 0), reverse=True)
    MEDIA_SESSIONS.set(uid, "server2_streams", resolved)
    MEDIA_SESSIONS.set(uid, "server2_errors", [])
    return resolved, []
class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_HEAD(self):
        p = self.path.split("?", 1)[0].strip("/").split("/")
        self.send_response(200)
        sid_h = p[1].split(".")[0] if len(p) >= 2 else ""
        if len(p) >= 2 and p[0] == "s" and sid_h in STREAMS_CACHE:
            u = STREAMS_CACHE[sid_h]["url"].lower()
            ctype = "application/dash+xml" if ".mpd" in u else ("application/vnd.apple.mpegurl" if ".m3u8" in u else "video/mp4")
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
    def do_GET(self):
        clean_path = self.path.split("?", 1)[0]
        if clean_path in ("/", "/app"):
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(app_portal.get_web_app_html(BASE_URL).encode()); return
        if clean_path == "/app/download":
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(app_portal.get_download_page_html(BASE_URL).encode()); return
        if clean_path == "/STxLEO_OTT.apk":
            apk_path = os.path.abspath("STxLEO_OTT.apk")
            if not os.path.exists(apk_path):
                apk_path = "/storage/emulated/0/Download/STxLEO_OTT.apk"
            if os.path.exists(apk_path):
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.android.package-archive")
                self.send_header("Content-Disposition", 'attachment; filename="STxLEO_OTT.apk"')
                self.send_header("Content-Length", str(os.path.getsize(apk_path)))
                self.end_headers()
                with open(apk_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            self.send_response(404); self.end_headers(); return
        if clean_path == "/manifest.json":
            self.send_response(200); self.send_header("Content-Type", "application/manifest+json; charset=utf-8"); self.end_headers()
            self.wfile.write(app_portal.get_manifest_json().encode()); return
        if clean_path == "/sw.js":
            self.send_response(200); self.send_header("Content-Type", "application/javascript; charset=utf-8"); self.end_headers()
            self.wfile.write(app_portal.get_sw_js().encode()); return
        if clean_path == "/health":
            self.send_response(200); self.end_headers(); self.wfile.write(b"OK"); return
        if clean_path.startswith("/api/"):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            def qv(k, d=""): return qs.get(k, [d])[0]
            api_cmd = clean_path.replace("/api/", "").strip("/")
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
            if api_cmd == "trending":
                try:
                    res = sites_scraper.search_custom_provider("ottstream", "Mirzapur") or sites_scraper.search_custom_provider("ottstream", "Stranger Things")
                    self.wfile.write(json.dumps({"results": res[:20]}).encode())
                except Exception as exc:
                    self.wfile.write(json.dumps({"results": [], "error": str(exc)}).encode())
                return
            if api_cmd == "search":
                q = qv("q")
                prov = qv("prov", "ottstream")
                try:
                    if prov == "ottstream":
                        res = sites_scraper.search_custom_provider("ottstream", q)
                    elif prov in ("vegamovies", "katmovieshd", "rogmovies"):
                        res = sites_scraper.search_custom_provider(prov, q)
                    else:
                        loop = asyncio.new_event_loop()
                        data = loop.run_until_complete(run_bridge("search", prov, q))
                        loop.close()
                        res = data.get("results", [])
                    filtered = filter_results(res, q)
                    self.wfile.write(json.dumps({"results": filtered}).encode())
                except Exception as exc:
                    self.wfile.write(json.dumps({"results": [], "error": str(exc)}).encode())
                return
            if api_cmd == "details":
                prov = qv("prov", "ottstream")
                item_id = urllib.parse.unquote(qv("id"))
                try:
                    if prov in ("ottstream", "vegamovies", "katmovieshd", "rogmovies", "hdhub4u"):
                        det = sites_scraper.get_custom_details(prov, item_id)
                    else:
                        loop = asyncio.new_event_loop()
                        det = loop.run_until_complete(run_bridge("details", prov, item_id))
                        loop.close()
                    self.wfile.write(json.dumps(det).encode())
                except Exception as exc:
                    self.wfile.write(json.dumps({"error": str(exc)}).encode())
                return
            if api_cmd == "streams":
                prov = qv("prov", "ottstream")
                item_id = urllib.parse.unquote(qv("id"))
                s = int(qv("s", "1"))
                e = int(qv("e", "1"))
                try:
                    if prov == "ottstream":
                        st = sites_scraper.get_ott_episode_streams(item_id, s, e)
                    else:
                        loop = asyncio.new_event_loop()
                        st = loop.run_until_complete(run_bridge("streams", prov, item_id, str(s), str(e)))
                        loop.close()
                    self.wfile.write(json.dumps(st).encode())
                except Exception as exc:
                    self.wfile.write(json.dumps({"streams": [], "error": str(exc)}).encode())
                return
            self.wfile.write(b"{}"); return

        parts = clean_path.strip("/").split("/")
        sid = parts[1].split(".")[0] if len(parts) >= 2 else ""
        if len(parts) < 2 or sid not in STREAMS_CACHE:
            self.send_response(404); self.end_headers(); self.wfile.write(b"Link expired. Search again."); return
        act = parts[0]
        info = STREAMS_CACHE[sid]
        u_low = info["url"].lower()
        is_mpd = ".mpd" in u_low
        is_hls = ".m3u8" in u_low
        ext = ".mpd" if is_mpd else (".m3u8" if is_hls else "")
        surl = f"{BASE_URL}/s/{sid}{ext}"
        hdrs = {k: v for k, v in (info.get("headers") or []) if len((k, v)) == 2}
        if act == "vlc":
            is_embed = any(k in u_low for k in ["embed", "vidsrc", "autoembed", "multiembed"])
            if is_embed:
                page = (
                    f'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
                    f'<title>{esc(info["title"])} - ST×LEO OTT</title>'
                    f'<style>*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;background:#090d16;color:#f8fafc;font-family:system-ui,sans-serif;padding:12px;text-align:center}}'
                    f'.card{{max-width:760px;margin:0 auto;background:#0f172a;border:1px solid rgba(255,255,255,.1);border-radius:18px;padding:16px;box-shadow:0 20px 40px rgba(0,0,0,0.8)}}'
                    f'.badge{{display:inline-block;background:rgba(229,9,20,.2);color:#fb7185;padding:4px 12px;border-radius:99px;font-size:12px;font-weight:700;margin-bottom:6px}}'
                    f'.player{{position:relative;width:100%;aspect-ratio:16/9;background:#000;border-radius:12px;overflow:hidden;margin:10px 0}}'
                    f'.player iframe{{position:absolute;top:0;left:0;width:100%;height:100%;border:none}}'
                    f'.btn{{display:block;width:100%;max-width:360px;margin:9px auto;padding:13px;border-radius:12px;text-decoration:none;font-weight:700;font-size:15px}}'
                    f'.v{{background:#e50914;color:#fff}}.v2{{background:#1e293b;color:#38bdf8;border:1px solid #334155}}'
                    f'.ft{{margin-top:14px;font-size:13px}}.ft a{{color:#fb7185;text-decoration:none;font-weight:600}}</style></head>'
                    f'<body><div class="card">'
                    f'<div class="badge">⚡ ST×LEO OTT LIVE • {esc(info["qual"])}</div>'
                    f'<h2 style="margin:4px 0 8px">🎬 {esc(info["title"])}</h2>'
                    f'<div class="player"><iframe src="{esc(info["url"])}" allowfullscreen allow="autoplay; fullscreen; picture-in-picture" referrerpolicy="no-referrer"></iframe></div>'
                    f'<a class="btn v" href="{esc(info["url"])}" target="_blank">▶️ Open Fullscreen in Browser</a>'
                    f'<a class="btn v2" href="/app">📱 Back to ST×LEO App</a>'
                    f'<div class="ft"><a href="https://t.me/Dara_OG">⚡ Developed by Devanshu (@Dara_OG)</a></div>'
                    f'</div></body></html>'
                )
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
                self.wfile.write(page.encode()); return
            itype = "application/dash+xml" if is_mpd else "video/*"
            ilink = f"intent://{HOST}/s/{sid}{ext}#Intent;scheme=https;package=org.videolan.vlc;type={itype};end"
            vlink = f"vlc://{HOST}/s/{sid}{ext}"
            djs = '<script src="https://cdn.dashjs.org/latest/dash.all.min.js"></script>' if is_mpd else ('<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>' if is_hls else "")
            dinit = f'<script>dashjs.MediaPlayer().create().initialize(document.getElementById("v"),"{surl}",true);</script>' if is_mpd else (f'<script>var v=document.getElementById("v");if(Hls.isSupported()){{var h=new Hls();h.loadSource("{surl}");h.attachMedia(v);}}else{{v.src="{surl}";}}</script>' if is_hls else "")
            src = "" if (is_mpd or is_hls) else f'src="{surl}"'
            trks = "".join(f'<track kind="subtitles" label="{esc(c["name"])}" src="{BASE_URL}/sub/{sid}/{i}">' for i, c in enumerate(info.get("captions", [])[:5]))
            meta = f'⭐ {esc(info["rating"])} • ' if info.get("rating") else ""
            h265_note = '<p style="font-size:12px;color:#fbbf24">⚠️ H.265: If screen is black, tap ⋮ → Open in Chrome → Open in VLC App</p>' if "h265" in u_low or "hevc" in str(info.get("codec", "")).lower() else ""
            dl_btn = '<p style="font-size:12px;color:#94a3b8;margin:8px 0">ℹ️ MPD stream: tap Open in VLC App to play (use MP4 to download)</p>' if is_mpd else f'<a class="btn d" href="{BASE_URL}/dl/{sid}">⬇️ Download Video</a>'
            page = (
                f'<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{esc(info["title"])}</title>{djs}'
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
                f'<h2 style="margin:4px 0 8px">🎬 {esc(info["title"])}</h2>{h265_note}'
                f'<video id="v" controls autoplay playsinline crossorigin="anonymous" {src}>{trks}</video>{dinit}'
                f'<div class="row"><button onclick="v.currentTime-=10">⏪ 10s</button><button onclick="v.currentTime+=10">⏩ 10s</button><button onclick="lk.style.display=\'block\'">🔒 Lock</button></div>'
                f'<div class="row"><button onclick="v.playbackRate=0.75">0.75x</button><button onclick="v.playbackRate=1">1x</button><button onclick="v.playbackRate=1.25">1.25x</button><button onclick="v.playbackRate=1.5">1.5x</button><button onclick="v.playbackRate=2">2x</button></div>'
                f'<div class="sliders"><label>☀️ Brightness <input type="range" min="0.3" max="1.6" step="0.05" value="1" oninput="v.style.filter=\'brightness(\'+this.value+\')\'" ></label>'
                f'<label>🔊 Volume <input type="range" min="0" max="1" step="0.05" value="1" oninput="v.volume=this.value"></label></div>'
                f'<a class="btn v" href="{ilink}">▶️ Open in VLC App</a>'
                f'<a class="btn v2" href="{vlink}">🔗 VLC Direct Link</a>'
                f'{dl_btn}'
                f'<div class="ft"><a href="https://t.me/Dara_OG">⚡ Made by @Dara_OG</a></div></div></body></html>'
            )
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(page.encode()); return
        if act == "sub" and len(parts) >= 3:
            idx = int(parts[2]); caps = info.get("captions", [])
            if idx < len(caps):
                try:
                    txt = httpx.get(caps[idx]["url"], follow_redirects=True, timeout=15.0).text
                    if not txt.lstrip().startswith("WEBVTT"): txt = "WEBVTT\n\n" + re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", txt)
                    self.send_response(200); self.send_header("Content-Type", "text/vtt; charset=utf-8"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
                    self.wfile.write(txt.encode()); return
                except Exception: pass
            self.send_response(404); self.end_headers(); return
        if act == "s" and ".mpd" in info["url"].lower():
            try:
                xml = httpx.get(info["url"], headers=hdrs, follow_redirects=True, timeout=15.0).text
                base = f"{BASE_URL}/seg/{sid}/"
                xml = re.sub(r"<BaseURL>[^<]*</BaseURL>", "", xml)
                xml = re.sub(r"(<MPD[^>]*>)", rf"\1<BaseURL>{base}</BaseURL>", xml, count=1)
                self.send_response(200); self.send_header("Content-Type", "application/dash+xml"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
                self.wfile.write(xml.encode()); return
            except Exception:
                self.send_response(502); self.end_headers(); return
        if act == "dl" and not is_mpd and not is_hls:
            if not hdrs:
                self.send_response(302); self.send_header("Location", info["url"]); self.end_headers(); return
        if act == "s" and not is_mpd and not is_hls and not hdrs:
            self.send_response(302); self.send_header("Location", info["url"]); self.end_headers(); return
        if act in ("s", "dl", "seg"):
            target = info["url"]
            if act == "seg":
                sub = "/".join(parts[2:])
                if "?" in self.path: sub += "?" + self.path.split("?", 1)[1]
                target = info["url"].rsplit("/", 1)[0] + "/" + sub
            if "Range" in self.headers: hdrs["Range"] = self.headers["Range"]
            try:
                client = HTTP_POOL
                if True:
                    with client.stream("GET", target, headers=hdrs) as r:
                        if r.status_code in (403, 428, 429) and any(k.lower() == "referer" for k in hdrs):
                            hdrs2 = {k: v for k, v in hdrs.items() if k.lower() != "referer"}
                            with client.stream("GET", target, headers=hdrs2) as r2:
                                self.send_response(r2.status_code)
                                for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                                    if h in r2.headers: self.send_header(h, r2.headers[h])
                                self.send_header("Access-Control-Allow-Origin", "*")
                                if act == "dl":
                                    ext = ".mpd" if ".mpd" in info["url"].lower() else (".m3u8" if ".m3u8" in info["url"].lower() else ".mp4")
                                    self.send_header("Content-Disposition", f'attachment; filename="{info["safe"]}{ext}"')
                                self.end_headers()
                                for chunk in r2.iter_bytes(262144): self.wfile.write(chunk)
                                return
                        self.send_response(r.status_code)
                        for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                            if h in r.headers: self.send_header(h, r.headers[h])
                        self.send_header("Access-Control-Allow-Origin", "*")
                        if act == "dl":
                            ext = ".mpd" if ".mpd" in info["url"].lower() else (".m3u8" if ".m3u8" in info["url"].lower() else ".mp4")
                            self.send_header("Content-Disposition", f'attachment; filename="{info["safe"]}{ext}"')
                        self.end_headers()
                        for chunk in r.iter_bytes(262144): self.wfile.write(chunk)
            except Exception: pass
def start_server(): ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), ProxyHandler).serve_forever()
async def safe_edit(q, text, markup=None, force_text=False):
    if q.message.photo and force_text:
        await q.message.delete()
        await q.message.reply_text(text[:4090], reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
    elif q.message.photo: await q.edit_message_caption(caption=text[:1020], reply_markup=markup, parse_mode="HTML")
    else: await q.edit_message_text(text=text[:4090], reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)

def ensure_bridge():
    if not os.path.exists(BRIDGE) or not os.access(BRIDGE, os.X_OK):
        logger.info("tg_bridge not found or not executable, downloading...")
        try:
            import urllib.request
            url = "https://github.com/devanshudara0-cpu/moviebox-tg-bot-/releases/latest/download/tg_bridge"
            urllib.request.urlretrieve(url, BRIDGE)
            os.chmod(BRIDGE, 0o755)
            logger.info("tg_bridge downloaded successfully!")
        except Exception as e:
            logger.error("Failed to download tg_bridge: %s", e)

async def run_bridge(*args):
    ensure_bridge()
    try:
        res = await asyncio.to_thread(subprocess.run, [BRIDGE, *args], capture_output=True, text=True, timeout=90)
        return {"error": res.stderr[:800] or "Bridge error"} if res.returncode != 0 else json.loads(res.stdout)
    except Exception as exc:
        logger.error("run_bridge failed: %s", exc)
        return {"error": str(exc)}

async def app_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not allowed(uid): return
    kb = [
        [InlineKeyboardButton("📱 Open ST×LEO OTT Web App", url=f"{BASE_URL}/app")],
        [InlineKeyboardButton("📲 Download Android App (.apk)", url=f"{BASE_URL}/app/download")],
        [InlineKeyboardButton("💬 Join Telegram (@Dara_OG)", url="https://t.me/Dara_OG")]
    ]
    await update.message.reply_text(
        f"🌟 <b>ST×LEO OTT (Android & Web App)</b>\n\n"
        f"👑 <b>Developer:</b> Devanshu (<code>@Dara_OG</code>)\n\n"
        f"⚡ <b>Features:</b>\n"
        f"• Stream Netflix, Prime Video, Hotstar & Latest Movies\n"
        f"• Watch live without downloading\n"
        f"• 1080p / 4K Player with VLC & External Player support\n"
        f"• 1-Click Fast Direct Cloud Downloads\n\n"
        f"<i>Tap below to open or install:</i>{FOOTER}",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="HTML"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Open ST×LEO OTT App", url=f"{BASE_URL}/app")],
        [InlineKeyboardButton("📲 Download Android APK", url=f"{BASE_URL}/app/download")],
        [InlineKeyboardButton("💬 Channel (@Dara_OG)", url="https://t.me/Dara_OG")]
    ])
    if uid == ADMIN_ID:
        await update.message.reply_text(f"👑 <b>Admin Mode Ready</b>\n• Send movie/series name\n• <code>/app</code> | <code>/trending</code> | <code>/fav</code> | <code>/history</code>\n\n<b>Admin:</b>\n• <code>/allow &lt;id&gt;</code>\n• <code>/remove &lt;id&gt;</code>\n• <code>/users</code>{FOOTER}", reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    elif allowed(uid):
        await update.message.reply_text(f"🎬 <b>ST×LEO FINAL BOSS Bot</b>\n• Send any movie/series name\n• <code>/app</code> | <code>/trending</code> | <code>/fav</code> | <code>/history</code>{FOOTER}", reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
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

async def setdomain_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or len(context.args) < 2:
        await update.message.reply_text("💡 Usage: <code>/setdomain vegamovies https://new-domain.com</code>\nAvailable: <code>vegamovies</code>, <code>rogmovies</code>, <code>katmovieshd</code>, <code>hdhub4u</code>", parse_mode="HTML")
        return
    site = context.args[0].lower().strip()
    url = context.args[1].strip()
    ok = sites_scraper.save_domain(site, url)
    if ok:
        await update.message.reply_text(f"✅ Domain for <b>{site}</b> updated to:\n<code>{url}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ Failed to update domain.", parse_mode="HTML")

async def domains_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not allowed(update.effective_user.id): return
    doms = sites_scraper.load_domains()
    txt = "🌐 <b>Current Server Domains:</b>\n\n"
    for k, v in doms.items():
        txt += f"• <b>{k}</b>: <code>{v}</code>\n"
    txt += f"\n<i>Admin command to update:</i>\n<code>/setdomain &lt;server&gt; &lt;url&gt;</code>{FOOTER}"
    await update.message.reply_text(txt, parse_mode="HTML", disable_web_page_preview=True)

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

async def do_search(msg_obj, uid, query, prov="ottstream", edit=False):
    try:
        SESSIONS[uid] = {"query": query, "prov": prov}
        if prov == "ottstream":
            custom_results = await asyncio.to_thread(sites_scraper.search_custom_provider, "ottstream", query)
            data = {"results": custom_results}
        elif prov in ("vegamovies", "katmovieshd", "rogmovies"):
            custom_results = await asyncio.to_thread(sites_scraper.search_custom_provider, prov, query)
            data = {"results": custom_results}
        elif prov == "fourkhdhub":
            data = await run_bridge("search", prov, query)
            if not data.get("results"):
                custom_results = await asyncio.to_thread(sites_scraper.search_custom_provider, "hdhub4u", query)
                if custom_results:
                    data = {"results": custom_results}
        else:
            data = await run_bridge("search", prov, query)
        results = filter_results(data.get("results", []), query)
        SESSIONS[uid]["results"] = results
        lbl = dict(PROVIDERS).get(prov, prov)
        if data.get("error"): text = f"🔎 <b>{esc(query)}</b> • <code>{lbl}</code>\n❌ {esc(data['error'])}{FOOTER}"
        elif not results: text = f"🔎 <b>{esc(query)}</b> • <code>{lbl}</code>\n😕 No exact match. Try another server:{FOOTER}"
        else: text = f"🍿 <b>Search Results</b> • <code>{lbl}</code>\n🔎 <i>{esc(query)}</i>\n\nPick a title below:{FOOTER}"
        markup = results_kb(results, prov)
        await (msg_obj.edit_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True) if edit else msg_obj.reply_text(text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True))
    except Exception as exc:
        logger.error("do_search error: %s", exc)
        await msg_obj.reply_text(f"❌ Error during search: <code>{esc(str(exc))}</code>{FOOTER}", parse_mode="HTML")

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not allowed(uid): return
    try:
        data = await run_bridge("trending")
        results = data.get("results", [])
        SESSIONS[uid] = {"query": "Trending", "prov": "moviebox", "results": results}
        if not results:
            err = data.get("error", "Could not load trending.")
            await update.message.reply_text(f"❌ {esc(err)}{FOOTER}", parse_mode="HTML")
            return
        await update.message.reply_text(f"🔥 <b>Trending Now</b>{FOOTER}", reply_markup=results_kb(results), parse_mode="HTML", disable_web_page_preview=True)
    except Exception as exc:
        logger.error("trending_cmd error: %s", exc)
        await update.message.reply_text(f"❌ Error: <code>{esc(str(exc))}</code>{FOOTER}", parse_mode="HTML")

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
    sz = f" • {s['size_str']}" if s.get("size_str") else (f" • {s['size_mb']}MB" if s.get("size_mb") else "")
    lang = f" • {s['language']}" if s.get("language") else ""
    u = s.get("url", "").lower()
    if any(k in u for k in ["vcloud", "hubcloud", "hubdrive", "fastdl", "gofile", "megaup", "filebee", "vikingfile", "1fichier", "nexdrive", "greenmotors"]):
        fmt = " ☁️ [Cloud]"
    elif ".mpd" in u or s.get("format") == "dash":
        fmt = " [MPD]"
    elif ".m3u8" in u or s.get("format") == "hls":
        fmt = " [HLS]"
    else:
        fmt = " [MP4]"
    return f"🎞 {q}{sz}{lang}{fmt}"[:60]

def dedupe_streams(streams):
    seen = set()
    out = []
    for s in streams or []:
        sig = (s.get("resolution") or s.get("quality"), s.get("size_str") or s.get("size_mb"), s.get("language"))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(s)
    return out if out else (streams or [])

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

async def show_details(q, sess, d, uid=0):
    sess["details"] = d; hdr = info_header(d); seasons = d.get("seasons", [])
    if seasons:
        sess["seasons"] = seasons
        kb = [[InlineKeyboardButton(f"📂 Season {s['number']} ({len(s['episodes'])} eps)", callback_data=f"s:{i}")] for i, s in enumerate(seasons)]
        kb.append([InlineKeyboardButton("⭐ Save", callback_data="save"), InlineKeyboardButton("⬅️ Back", callback_data="back:res")])
        await safe_edit(q, f"{hdr}\n\nChoose a season:{FOOTER}", InlineKeyboardMarkup(kb))
    else:
        streams = dedupe_streams(d.get("streams", []))
        prov = sess.get("item", {}).get("provider") or sess.get("prov")
        s2_errors = []
        if prov == "fourkhdhub" and streams:
            streams, s2_errors = await resolve_server2_streams(uid, streams)
            streams = dedupe_streams(streams)
        sess["streams"], sess["captions"] = streams, d.get("captions", [])
        if not streams:
            reason = f"\n<i>{esc('; '.join(s2_errors[:2]))}</i>" if s2_errors else ""
            await safe_edit(q, f"{hdr}\n\n❌ <b>No playable streams found.</b>{reason}{FOOTER}", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back:res")]])); return
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
            if item.get("provider") in ("ottstream", "vegamovies", "katmovieshd", "rogmovies", "hdhub4u"):
                d = await asyncio.to_thread(sites_scraper.get_custom_details, item["provider"], item["id"])
            else:
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
                sess["details_raw"] = d
                sess["dubs"] = dubs
                kb = [[InlineKeyboardButton(f"🎙 {x.get('label') or x.get('language')}", callback_data=f"dub:{i}")] for i, x in enumerate(dubs)]
                kb.append([InlineKeyboardButton("⬅️ Back", callback_data="back:res")])
                await safe_edit(q, f"{info_header(d)}\n\nSelect audio language:{FOOTER}", InlineKeyboardMarkup(kb))
            else: await show_details(q, sess, d, uid=uid)
        elif data.startswith("dub:"):
            dub = sess["dubs"][int(data.split(":")[1])]
            await safe_edit(q, f"⏳ Loading <b>{esc(dub.get('label') or dub.get('language'))}</b>...{FOOTER}")
            if sess["item"].get("provider") in ("ottstream", "vegamovies", "katmovieshd", "rogmovies", "hdhub4u"):
                d = dict(sess.get("details_raw", {}))
                d["streams"] = dedupe_streams(dub.get("streams", []))
            else:
                sess["item"]["id"] = dub["id"]
                d = await run_bridge("details", sess["item"]["provider"], dub["id"])
                if d.get("error"): await safe_edit(q, f"❌ {esc(d['error'])}{FOOTER}"); return
            await show_details(q, sess, d, uid=uid)
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
            if item.get("provider") == "ottstream":
                res = await asyncio.to_thread(sites_scraper.get_ott_episode_streams, item["id"], ep["season"], ep["number"])
                streams = res.get("streams", [])
            else:
                res = await run_bridge("streams", item["provider"], item["id"], str(ep["season"]), str(ep["number"]))
                streams = res.get("streams", [])
            prov = item.get("provider") or sess.get("prov")
            s2_errors = []
            if prov == "fourkhdhub" and streams:
                streams, s2_errors = await resolve_server2_streams(uid, streams)
            streams = dedupe_streams(streams)
            sess["streams"], sess["captions"] = streams, res.get("captions", [])
            if not streams:
                reason = f"\n<i>{esc('; '.join(s2_errors[:2]))}</i>" if s2_errors else ""
                await safe_edit(q, f"❌ No playable streams found.{reason}{FOOTER}", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back:eps")]])); return
            await safe_edit(q, f"📺 <b>{esc(item['title'])}</b> • S{ep['season']:02d}E{ep['number']:02d}\nSelect quality:{FOOTER}", quality_kb(streams, "back:eps"))
        elif data.startswith("q:"):
            idx = int(data.split(":")[1]); st = sess["streams"][idx]
            if not str(st.get("url", "")).startswith(("http://", "https://")):
                await safe_edit(q, f"❌ Invalid or unavailable stream URL.{FOOTER}", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back:q")]])); return
            qual = st.get("quality") or f"{st.get('resolution', '')}p"; title = sess["item"]["title"]
            save_history(uid, sess["item"]); sid = uuid.uuid4().hex[:8]
            safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{title}_{qual}")
            d = sess.get("details", {})
            raw_url = st["url"]
            direct_url = raw_url
            if any(k in raw_url.lower() for k in ["nexdrive", "fastdl", "greenmotors", "hubcloud", "hubdrive"]):
                try:
                    direct_url = await asyncio.to_thread(sites_scraper.resolve_direct_stream, raw_url)
                except Exception as exc:
                    logger.warning("direct resolution failed: %s", exc)

            STREAMS_CACHE[sid] = {"url": direct_url, "raw_url": raw_url, "headers": st.get("headers"), "codec": st.get("codec"), "title": title, "qual": qual, "safe": safe, "rating": d.get("rating"), "captions": sess.get("captions", [])}
            is_embed = any(k in str(direct_url).lower() for k in ["embed", "vidsrc", "autoembed", "multiembed"])
            if is_embed:
                kb = [
                    [InlineKeyboardButton("▶️ Watch Live (Ad-Free Cinema)", url=f"{BASE_URL}/vlc/{sid}")],
                    [InlineKeyboardButton("📱 Open in ST×LEO OTT App", url=f"{BASE_URL}/app")],
                    [InlineKeyboardButton("🌐 Direct Embed Stream", url=direct_url)],
                ]
            else:
                kb = [
                    [InlineKeyboardButton("▶️ Watch / Open in VLC", url=f"{BASE_URL}/vlc/{sid}")],
                    [InlineKeyboardButton("⬇️ 1-Click Direct Download", url=f"{BASE_URL}/dl/{sid}")],
                ]
                if direct_url != raw_url and str(direct_url).startswith("http"):
                    kb.append([InlineKeyboardButton("🚀 Direct High-Speed Link", url=direct_url)])
                elif any(k in raw_url.lower() for k in ["vcloud", "hubcloud", "hubdrive", "fastdl", "gofile", "megaup", "filebee", "vikingfile"]):
                    kb.append([InlineKeyboardButton("⚡ Fast Cloud Link", url=raw_url)])
            if sess.get("season") and sess.get("e_idx", -1) + 1 < len(sess["season"]["episodes"]):
                kb.append([InlineKeyboardButton("⏭ Next Episode", callback_data=f"e:{sess['e_idx']+1}")])
            kb.append([InlineKeyboardButton("🔗 Copy URL", callback_data=f"url:{idx}"), InlineKeyboardButton("⬅️ Back", callback_data="back:q")])
            await safe_edit(q, f"🎬 <b>{esc(title)}</b>\n🎞 Quality: <b>{esc(qual)}</b>\n\nTap below to play or download:{FOOTER}", InlineKeyboardMarkup(kb))
        elif data == "back:res":
            await safe_edit(q, f"🍿 <b>{esc(sess.get('query', 'Results'))}</b>\nPick a title:{FOOTER}", results_kb(sess.get("results", []), sess.get("prov")), force_text=True)
        elif data == "back:seasons": await show_details(q, sess, sess["details"], uid=uid)
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

if __name__ == "__main__":
    if not TOKEN:
        raise KeyError("TELEGRAM_TOKEN")
    threading.Thread(target=start_server, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("app", app_cmd))
    app.add_handler(CommandHandler("trending", trending_cmd))
    app.add_handler(CommandHandler("fav", fav_cmd))
    app.add_handler(CommandHandler("history", hist_cmd))
    app.add_handler(CommandHandler("allow", allow))
    app.add_handler(CommandHandler("remove", remove))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(CommandHandler("setdomain", setdomain_cmd))
    app.add_handler(CommandHandler("domains", domains_cmd))
    app.add_handler(CommandHandler("movie", movie_search))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    ensure_bridge()
    app.run_polling()
        
