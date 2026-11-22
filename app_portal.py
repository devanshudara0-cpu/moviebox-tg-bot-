import json

def get_manifest_json():
    return json.dumps({
        "name": "ST×LEO OTT",
        "short_name": "ST×LEO",
        "description": "Stream Movies & Series Live without download",
        "start_url": "/app",
        "display": "standalone",
        "background_color": "#090d16",
        "theme_color": "#e50914",
        "icons": [
            {
                "src": "/logo.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/logo.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }, indent=2)

def get_sw_js():
    return """
const CACHE_NAME = 'stleo-ott-v2';
self.addEventListener('install', (e) => {
    self.skipWaiting();
});
self.addEventListener('activate', (e) => {
    e.waitUntil(clients.claim());
});
self.addEventListener('fetch', (e) => {
    // Pass-through network requests
});
"""

def get_download_page_html(base_url: str):
    return f"""<!doctype html>
<html lang="hi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Download ST×LEO OTT App - Android APK & WebAPK</title>
    <link rel="icon" href="{base_url}/logo.png">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: radial-gradient(circle at top, #1e1b4b, #090d16 70%);
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 20px;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .card {{
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 24px;
            max-width: 520px;
            width: 100%;
            padding: 30px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.6);
        }}
        .logo {{
            width: 80px;
            height: 80px;
            border-radius: 20px;
            box-shadow: 0 8px 24px rgba(229, 9, 20, 0.4);
            margin-bottom: 16px;
        }}
        h1 {{
            font-size: 26px;
            font-weight: 800;
            margin-bottom: 6px;
            background: linear-gradient(135deg, #fff, #fb7185);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .dev-badge {{
            display: inline-block;
            background: rgba(229, 9, 20, 0.15);
            color: #fb7185;
            font-size: 13px;
            font-weight: 600;
            padding: 4px 14px;
            border-radius: 99px;
            margin-bottom: 20px;
            border: 1px solid rgba(229, 9, 20, 0.3);
        }}
        .desc {{
            color: #94a3b8;
            font-size: 14px;
            line-height: 1.6;
            margin-bottom: 24px;
        }}
        .btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            width: 100%;
            padding: 15px;
            border-radius: 14px;
            font-size: 16px;
            font-weight: 700;
            text-decoration: none;
            margin-bottom: 12px;
            transition: all 0.2s ease;
        }}
        .btn-apk {{
            background: linear-gradient(135deg, #e50914, #b91c1c);
            color: #fff;
            box-shadow: 0 8px 20px rgba(229, 9, 20, 0.4);
        }}
        .btn-pwa {{
            background: #1e293b;
            color: #38bdf8;
            border: 1px solid #334155;
        }}
        .btn-tg {{
            background: rgba(14, 165, 233, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(14, 165, 233, 0.3);
        }}
        .steps {{
            background: #0f172a;
            border-radius: 14px;
            padding: 16px;
            margin-top: 20px;
            text-align: left;
            font-size: 13px;
            color: #cbd5e1;
        }}
        .steps ol {{
            margin-left: 20px;
            margin-top: 8px;
            line-height: 1.7;
        }}
    </style>
</head>
<body>
    <div class="card">
        <img class="logo" src="{base_url}/logo.png" alt="ST×LEO OTT">
        <h1>ST×LEO OTT</h1>
        <div class="dev-badge">Developed by Devanshu (@Dara_OG)</div>
        <p class="desc">
            Latest Movies & Webseries ko bina kisi download aur login ke seedha HD / 4K me stream karein!
        </p>

        <a class="btn btn-apk" href="{base_url}/STxLEO_OTT.apk" download="STxLEO_OTT.apk">
            📲 Download Android APK (.apk)
        </a>

        <a class="btn btn-pwa" href="{base_url}/app">
            🌐 Open Web App (PWA Instant)
        </a>

        <a class="btn btn-tg" href="https://t.me/Dara_OG" target="_blank">
            💬 Join Telegram (@Dara_OG)
        </a>

        <div class="steps">
            <strong>💡 How to Install on Phone:</strong>
            <ol>
                <li>Tap <b>Download Android APK</b> to install the real app.</li>
                <li>Or tap <b>Open Web App</b> ➔ Chrome menu ⋮ ➔ <b>"Install App"</b>.</li>
                <li>App phone me real app ki tarah install ho jayegi!</li>
            </ol>
        </div>
    </div>
</body>
</html>
"""

def get_web_app_html(base_url: str):
    return f"""<!doctype html>
<html lang="hi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
    <title>ST×LEO OTT - Stream Movies & Series</title>
    <meta name="theme-color" content="#e50914">
    <link rel="manifest" href="{base_url}/manifest.json">
    <link rel="icon" href="{base_url}/logo.png">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: #090d16;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            min-height: 100vh;
            padding-bottom: 60px;
            overflow-x: hidden;
            -webkit-overflow-scrolling: touch;
            overscroll-behavior-y: none;
        }}
        header {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(9, 13, 22, 0.95);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            padding: 12px 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .brand {{
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
            color: inherit;
        }}
        .brand img {{
            width: 36px;
            height: 36px;
            border-radius: 9px;
            box-shadow: 0 4px 12px rgba(229, 9, 20, 0.3);
        }}
        .brand-text h1 {{
            font-size: 18px;
            font-weight: 900;
            letter-spacing: 0.5px;
            background: linear-gradient(135deg, #fff, #fb7185);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .brand-text span {{
            font-size: 10px;
            color: #94a3b8;
            display: block;
        }}
        .header-actions {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .install-btn {{
            display: none;
            background: #e50914;
            color: #fff;
            border: none;
            padding: 6px 14px;
            border-radius: 99px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
        }}
        .tg-btn {{
            background: rgba(14, 165, 233, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(14, 165, 233, 0.3);
            padding: 6px 12px;
            border-radius: 99px;
            font-size: 12px;
            font-weight: 600;
            text-decoration: none;
        }}
        .hero {{
            padding: 24px 18px 12px;
            text-align: center;
            background: radial-gradient(circle at center, #1e1b4b 0%, #090d16 80%);
        }}
        .hero h2 {{
            font-size: 24px;
            font-weight: 800;
            margin-bottom: 8px;
        }}
        .hero p {{
            font-size: 13px;
            color: #94a3b8;
            margin-bottom: 18px;
        }}
        .search-container {{
            max-width: 600px;
            margin: 0 auto;
        }}
        .search-bar {{
            display: flex;
            background: rgba(15, 23, 42, 0.9);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0,0,0,0.5);
        }}
        .search-bar input {{
            flex: 1;
            background: transparent;
            border: none;
            padding: 14px 18px;
            color: #fff;
            font-size: 15px;
            outline: none;
        }}
        .search-bar button {{
            background: #e50914;
            border: none;
            padding: 0 20px;
            color: #fff;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
        }}
        .server-tabs {{
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding: 14px 18px;
            scrollbar-width: none;
        }}
        .server-tabs::-webkit-scrollbar {{ display: none; }}
        .tab {{
            background: #1e293b;
            color: #94a3b8;
            border: 1px solid #334155;
            padding: 8px 16px;
            border-radius: 99px;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s ease;
        }}
        .tab.active {{
            background: #e50914;
            color: #fff;
            border-color: #e50914;
            box-shadow: 0 4px 12px rgba(229, 9, 20, 0.4);
        }}
        .section-title {{
            font-size: 18px;
            font-weight: 700;
            padding: 14px 18px 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .section-title span {{
            font-size: 12px;
            color: #fb7185;
            font-weight: 700;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
            gap: 12px;
            padding: 8px 18px;
            transform: translateZ(0);
            will-change: transform;
        }}
        @media (min-width: 600px) {{
            .grid {{ grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 16px; }}
        }}
        .card {{
            background: #131a2a;
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.05);
            cursor: pointer;
            transition: transform 0.2s cubic-bezier(0.2, 0, 0, 1);
            position: relative;
            transform: translateZ(0);
            will-change: transform;
            contain: content;
        }}
        .card:hover {{ transform: translateY(-4px); }}
        .poster {{
            width: 100%;
            aspect-ratio: 2/3;
            object-fit: cover;
            background: #1e293b;
            display: block;
        }}
        .card-info {{
            padding: 8px;
        }}
        .card-title {{
            font-size: 13px;
            font-weight: 700;
            line-height: 1.3;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            margin-bottom: 4px;
        }}
        .card-meta {{
            font-size: 11px;
            color: #94a3b8;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .badge {{
            display: inline-block;
            font-size: 10px;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
            background: rgba(229, 9, 20, 0.2);
            color: #fb7185;
        }}
        /* Cinema Modal */
        .modal {{
            display: none;
            position: fixed;
            inset: 0;
            z-index: 999;
            background: rgba(0, 0, 0, 0.88);
            backdrop-filter: blur(10px);
            align-items: center;
            justify-content: center;
            padding: 12px;
        }}
        .modal-card {{
            background: #0f172a;
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 20px;
            max-width: 680px;
            width: 100%;
            max-height: 90vh;
            overflow-y: auto;
            position: relative;
            box-shadow: 0 25px 50px rgba(0,0,0,0.8);
        }}
        .close-btn {{
            position: absolute;
            top: 14px;
            right: 14px;
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
            border: none;
            width: 34px;
            height: 34px;
            border-radius: 99px;
            font-size: 18px;
            cursor: pointer;
            z-index: 10;
        }}
        .player-box {{
            width: 100%;
            aspect-ratio: 16/9;
            background: #000;
            border-radius: 20px 20px 0 0;
            overflow: hidden;
            position: relative;
        }}
        .player-box iframe, .player-box video {{
            width: 100%;
            height: 100%;
            border: none;
        }}
        .modal-body {{
            padding: 16px;
        }}
        .stream-btn {{
            display: block;
            width: 100%;
            background: #1e293b;
            color: #f8fafc;
            border: 1px solid #334155;
            padding: 12px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 700;
            text-align: left;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .stream-btn:hover {{
            background: #e50914;
            border-color: #e50914;
        }}
        .vlc-btn {{
            display: block;
            width: 100%;
            background: #ea580c;
            color: #fff;
            padding: 12px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 700;
            text-align: center;
            text-decoration: none;
            margin-top: 10px;
        }}
        .ep-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(70px, 1fr));
            gap: 6px;
            margin: 12px 0;
        }}
        .ep-btn {{
            background: #1e293b;
            color: #fff;
            border: 1px solid #334155;
            padding: 8px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
        }}
        .ep-btn.active {{
            background: #e50914;
            border-color: #e50914;
        }}
        .spinner {{
            display: none;
            text-align: center;
            padding: 30px;
            color: #fb7185;
            font-size: 15px;
            font-weight: 600;
        }}
    </style>
</head>
<body>
    <header>
        <a class="brand" href="/app">
            <img src="https://cdn-icons-png.flaticon.com/512/2503/2503508.png" alt="ST×LEO">
            <div class="brand-text">
                <h1>ST×LEO OTT</h1>
                <span>BY DEVANSHU (@DARA_OG)</span>
            </div>
        </a>
        <div class="header-actions">
            <button id="pwa-install" class="install-btn">📲 Install App</button>
            <a class="tg-btn" href="https://t.me/Dara_OG" target="_blank">💬 Channel</a>
        </div>
    </header>

    <div class="hero">
        <h2>Watch Movies & Series Live</h2>
        <p>Latest Movies & Webseries without download!</p>
        <div class="search-container">
            <div class="search-bar">
                <input type="text" id="query-input" placeholder="Type movie or series name...">
                <button onclick="doSearch()">Search</button>
            </div>
        </div>
    </div>

    <div class="server-tabs">
        <div class="tab active" data-prov="ottstream" onclick="switchServer('ottstream', this)">Server 1</div>
        <div class="tab" data-prov="moviebox" onclick="switchServer('moviebox', this)">Server 2</div>
        <div class="tab" data-prov="fourkhdhub" onclick="switchServer('fourkhdhub', this)">Server 3</div>
        <div class="tab" data-prov="vegamovies" onclick="switchServer('vegamovies', this)">Server 4</div>
        <div class="tab" data-prov="katmovieshd" onclick="switchServer('katmovieshd', this)">Server 5</div>
        <div class="tab" data-prov="rogmovies" onclick="switchServer('rogmovies', this)">Server 6</div>
    </div>

    <div class="section-title">
        <h3 id="section-heading">🔥 Popular & Trending Titles</h3>
        <span>LIVE</span>
    </div>

    <div id="loading" class="spinner">⏳ Loading content...</div>
    <div id="results-grid" class="grid"></div>

    <!-- Modal Cinema Player -->
    <div id="cinema-modal" class="modal">
        <div class="modal-card">
            <button class="close-btn" onclick="closeModal()">✕</button>
            <div id="player-container" class="player-box"></div>
            <div class="modal-body">
                <h2 id="modal-title" style="margin-bottom: 6px;"></h2>
                <div id="modal-meta" style="font-size: 13px; color: #94a3b8; margin-bottom: 12px;"></div>
                <p id="modal-plot" style="font-size: 13px; color: #cbd5e1; margin-bottom: 16px; line-height: 1.5;"></p>
                
                <div id="seasons-container" style="display: none; margin-bottom: 16px;">
                    <div style="font-size: 13px; font-weight: 700; color: #fb7185; margin-bottom: 6px;">📺 SELECT SEASON & EPISODE:</div>
                    <div id="seasons-tabs" style="display: flex; gap: 6px; margin-bottom: 8px;"></div>
                    <div id="episodes-list" class="ep-grid"></div>
                </div>

                <div style="font-size: 13px; font-weight: 700; color: #fb7185; margin-bottom: 8px;">⚡ SELECT QUALITY / STREAM:</div>
                <div id="streams-list"></div>
                <a id="vlc-action" class="vlc-btn" href="#" style="display: none;">▶️ Open in VLC Player</a>
            </div>
        </div>
    </div>

    <script>
        let currentProv = 'ottstream';
        let deferredPrompt;
        const grid = document.getElementById('results-grid');
        const loading = document.getElementById('loading');
        const modal = document.getElementById('cinema-modal');

        window.addEventListener('beforeinstallprompt', (e) => {{
            e.preventDefault();
            deferredPrompt = e;
            const btn = document.getElementById('pwa-install');
            btn.style.display = 'block';
            btn.addEventListener('click', () => {{
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then(() => {{
                    btn.style.display = 'none';
                }});
            }});
        }});

        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/sw.js').catch(() => {{}});
        }}

        document.getElementById('query-input').addEventListener('keypress', (e) => {{
            if (e.key === 'Enter') doSearch();
        }});

        function switchServer(prov, el) {{
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            el.classList.add('active');
            currentProv = prov;
            const q = document.getElementById('query-input').value.trim();
            if (q) doSearch();
        }}

        async function loadTrending() {{
            loading.style.display = 'block';
            grid.innerHTML = '';
            try {{
                const res = await fetch('/api/trending');
                const data = await res.json();
                renderCards(data.results || []);
            }} catch (e) {{
                grid.innerHTML = '<div style="padding:20px;color:#94a3b8">Failed to load trending.</div>';
            }} finally {{
                loading.style.display = 'none';
            }}
        }}

        async function doSearch() {{
            const q = document.getElementById('query-input').value.trim();
            if (!q) return;
            document.getElementById('section-heading').innerText = `🔎 Results for "${{q}}"`;
            loading.style.display = 'block';
            grid.innerHTML = '';
            try {{
                const res = await fetch(`/api/search?q=${{encodeURIComponent(q)}}&prov=${{currentProv}}`);
                const data = await res.json();
                renderCards(data.results || []);
            }} catch (e) {{
                grid.innerHTML = '<div style="padding:20px;color:#94a3b8">Search failed. Try another server.</div>';
            }} finally {{
                loading.style.display = 'none';
            }}
        }}

        function onPosterError(img, bgUrl) {{
            if (bgUrl && bgUrl.startsWith('http') && img.src !== bgUrl) {{
                img.src = bgUrl;
                return;
            }}
            const card = img.closest('.card');
            if (card) {{
                card.remove();
            }}
        }}

        function renderCards(items) {{
            if (!items || items.length === 0) {{
                grid.innerHTML = '<div style="padding:30px;color:#94a3b8;grid-column: 1/-1;text-align:center">No titles found. Try searching on another server.</div>';
                return;
            }}
            grid.innerHTML = items.map((it, idx) => {{
                let poster = it.poster;
                if (!poster || !poster.startsWith('http') || poster.includes('flaticon') || poster.includes('placeholder')) {{
                    const m = String(it.id || '').match(/tt\\d+/);
                    poster = m ? `https://images.metahub.space/poster/small/${{m[0]}}/img` : (it.background || '');
                }}
                if (!poster) return '';
                const yr = it.year ? it.year : '';
                const tp = it.type ? it.type : 'Movie';
                const bg = (it.background || '').replace(/'/g, "\\\\'");
                return `
                <div class="card" onclick="openDetails('${{it.provider || currentProv}}', '${{encodeURIComponent(it.id)}}')">
                    <img class="poster" src="${{poster}}" alt="${{it.title}}" loading="lazy" onerror="onPosterError(this, '${{bg}}')">
                    <div class="card-info">
                        <div class="card-title">${{it.title}}</div>
                        <div class="card-meta">
                            <span>${{yr}}</span>
                            <span class="badge">${{tp}}</span>
                        </div>
                    </div>
                </div>
            `}}).join('');
        }}

        let activeDetails = null;
        async function openDetails(prov, id) {{
            modal.style.display = 'flex';
            document.getElementById('modal-title').innerText = 'Loading...';
            document.getElementById('modal-meta').innerText = '';
            document.getElementById('modal-plot').innerText = '';
            document.getElementById('streams-list').innerHTML = '⏳ Loading streams...';
            document.getElementById('player-container').innerHTML = '';
            document.getElementById('seasons-container').style.display = 'none';
            document.getElementById('vlc-action').style.display = 'none';

            try {{
                const res = await fetch(`/api/details?prov=${{prov}}&id=${{id}}`);
                const data = await res.json();
                activeDetails = data;
                activeDetails.prov = prov;
                activeDetails.id = decodeURIComponent(id);

                document.getElementById('modal-title').innerText = data.title || 'Movie';
                document.getElementById('modal-meta').innerText = [data.year, data.rating ? '⭐ ' + data.rating : '', data.duration].filter(Boolean).join(' • ');
                document.getElementById('modal-plot').innerText = data.plot || '';

                if (data.seasons && data.seasons.length > 0) {{
                    renderSeasons(data.seasons);
                }} else if (data.streams && data.streams.length > 0) {{
                    renderStreams(data.streams);
                    playStream(data.streams[0].url, data.title);
                }} else {{
                    document.getElementById('streams-list').innerHTML = '<div style="color:#94a3b8">No direct streams found.</div>';
                }}
            }} catch (e) {{
                document.getElementById('modal-title').innerText = 'Error';
                document.getElementById('streams-list').innerHTML = 'Failed to load details.';
            }}
        }}

        function renderSeasons(seasons) {{
            const sContainer = document.getElementById('seasons-container');
            const sTabs = document.getElementById('seasons-tabs');
            sContainer.style.display = 'block';
            sTabs.innerHTML = seasons.map((s, idx) => `
                <button class="tab ${{idx === 0 ? 'active' : ''}}" onclick="selectSeason(${{idx}}, this)">Season ${{s.number}}</button>
            `).join('');
            renderEpisodes(seasons[0]);
        }}

        function selectSeason(idx, btn) {{
            document.querySelectorAll('#seasons-tabs .tab').forEach(t => t.classList.remove('active'));
            btn.classList.add('active');
            renderEpisodes(activeDetails.seasons[idx]);
        }}

        function renderEpisodes(season) {{
            const epList = document.getElementById('episodes-list');
            epList.innerHTML = season.episodes.map((ep, idx) => `
                <button class="ep-btn ${{idx === 0 ? 'active' : ''}}" onclick="fetchEpisodeStreams(${{ep.season}}, ${{ep.number}}, this)">E${{ep.number}}</button>
            `).join('');
            if (season.episodes.length > 0) {{
                fetchEpisodeStreams(season.episodes[0].season, season.episodes[0].number);
            }}
        }}

        async function fetchEpisodeStreams(s, e, btn) {{
            if (btn) {{
                document.querySelectorAll('#episodes-list .ep-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
            }}
            document.getElementById('streams-list').innerHTML = '⏳ Loading episode streams...';
            try {{
                const res = await fetch(`/api/streams?prov=${{activeDetails.prov}}&id=${{encodeURIComponent(activeDetails.id)}}&s=${{s}}&e=${{e}}`);
                const data = await res.json();
                renderStreams(data.streams || []);
                if (data.streams && data.streams.length > 0) {{
                    playStream(data.streams[0].url, `${{activeDetails.title}} S${{s}}E${{e}}`);
                }}
            }} catch (err) {{
                document.getElementById('streams-list').innerHTML = 'Failed to fetch episode streams.';
            }}
        }}

        function renderStreams(streams) {{
            const list = document.getElementById('streams-list');
            list.innerHTML = streams.map(st => `
                <button class="stream-btn" onclick="playStream('${{st.url}}', '${{activeDetails.title}}')">
                    ▶️ ${{st.quality || '1080p'}} • ${{st.language || 'Multi'}} • ${{st.size_str || 'Fast'}}
                </button>
            `).join('');
        }}

        function playStream(url, title) {{
            const p = document.getElementById('player-container');
            const vlcBtn = document.getElementById('vlc-action');
            if (!url) return;

            const isEmbed = url.includes('embed') || url.includes('vidsrc') || url.includes('autoembed') || url.includes('multiembed') || url.includes('vidlink') || url.includes('2embed');

            if (isEmbed) {{
                p.innerHTML = `<iframe src="${{url}}" allowfullscreen allow="autoplay; encrypted-media; fullscreen" referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-forms allow-presentation"></iframe>`;
                vlcBtn.style.display = 'block';
                vlcBtn.href = url;
                vlcBtn.innerText = '🌐 Open Stream in Fullscreen Browser';
            }} else if (url.includes('.mp4') || url.includes('.m3u8') || url.includes('.mpd')) {{
                p.innerHTML = `<video controls autoplay playsinline src="${{url}}"></video>`;
                vlcBtn.style.display = 'block';
                vlcBtn.href = `intent://${{window.location.host}}/play?u=${{encodeURIComponent(url)}}#Intent;scheme=https;package=org.videolan.vlc;type=video/*;end`;
                vlcBtn.innerText = '▶️ Open in VLC Player';
            }} else {{
                p.innerHTML = `
                    <div style="padding: 40px 20px; text-align: center; color: #f8fafc;">
                        <h3 style="margin-bottom: 12px; color: #fb7185;">⚡ Cloud Stream / Download Ready</h3>
                        <p style="font-size: 13px; color: #94a3b8; margin-bottom: 20px;">Tap below to start streaming or download directly:</p>
                        <a href="${{url}}" target="_blank" style="display: inline-block; background: #e50914; color: #fff; padding: 12px 24px; border-radius: 99px; text-decoration: none; font-weight: 700;">🚀 Open Direct Link</a>
                    </div>
                `;
                vlcBtn.style.display = 'block';
                vlcBtn.href = url;
                vlcBtn.innerText = '🚀 Open Direct Link in Browser / Player';
            }}
        }}

        function closeModal() {{
            modal.style.display = 'none';
            document.getElementById('player-container').innerHTML = '';
        }}

        loadTrending();
    </script>
</body>
</html>
"""
