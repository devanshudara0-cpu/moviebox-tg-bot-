import os
import json
import re
import base64
import urllib.parse
import urllib.request
import gzip
import logging

logger = logging.getLogger(__name__)

DOMAINS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "domains.json"))

DEFAULT_DOMAINS = {
    "vegamovies": "https://vegamovies.latino",
    "rogmovies": "https://rogmovies.beauty",
    "katmovieshd": "https://katmoviehd.to",
    "hdhub4u": "https://4khdhub.one",
}

def load_domains() -> dict:
    domains = dict(DEFAULT_DOMAINS)
    if os.path.exists(DOMAINS_FILE):
        try:
            with open(DOMAINS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                domains.update(saved)
        except Exception as e:
            logger.error("Failed to load domains.json: %s", e)
    return domains

def save_domain(site_key: str, new_url: str) -> bool:
    site_key = site_key.lower().strip()
    new_url = new_url.strip().rstrip("/")
    if not (new_url.startswith("http://") or new_url.startswith("https://")):
        new_url = "https://" + new_url
    domains = load_domains()
    domains[site_key] = new_url
    try:
        with open(DOMAINS_FILE, "w", encoding="utf-8") as f:
            json.dump(domains, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to save domains.json: %s", e)
        return False

def get_domain(site_key: str) -> str:
    domains = load_domains()
    return domains.get(site_key, DEFAULT_DOMAINS.get(site_key, ""))

def fetch_html(url: str, timeout: int = 12) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.info().get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                return gzip.decompress(raw).decode("utf-8", errors="ignore")
            return raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("fetch_html failed for %s: %s", url, exc)
        return ""

def fetch_json(url: str, timeout: int = 10):
    text = fetch_html(url, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception as exc:
        logger.warning("fetch_json parse error for %s: %s", url, exc)
        return None

def search_ts_backend(provider_key: str, domain: str, query: str) -> list:
    encoded_q = urllib.parse.quote(query)
    url = f"{domain}/ts-search.php?q={encoded_q}&page=1"
    data = fetch_json(url)
    results = []
    if not data or "hits" not in data:
        return results
    for hit in data.get("hits", []):
        doc = hit.get("document", {})
        title = doc.get("post_title") or ""
        permalink = doc.get("permalink") or ""
        if not permalink:
            continue
        full_url = permalink if permalink.startswith("http") else urllib.parse.urljoin(domain, permalink)
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", title)
        year = int(year_match.group(1)) if year_match else None
        is_series = "season" in title.lower() or "s0" in title.lower() or "series" in title.lower()
        results.append({
            "provider": provider_key,
            "title": title,
            "id": full_url,
            "type": "Series" if is_series else "Movie",
            "year": year,
            "poster": doc.get("post_thumbnail"),
        })
    return results

def search_wordpress(provider_key: str, domain: str, query: str) -> list:
    encoded_q = urllib.parse.quote(query)
    url = f"{domain}/?s={encoded_q}"
    html = fetch_html(url)
    results = []
    if not html:
        return results

    articles = re.findall(r'<article[^>]*>([\s\S]*?)</article>', html)
    seen = set()
    if articles:
        for art in articles:
            m_link = re.search(r'<a[^>]+href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>', art, re.DOTALL)
            if not m_link:
                continue
            link = m_link.group(1)
            if link in seen or any(bad in link for bad in ["/category/", "/tag/", "/page/", "/author/", "/wp-content/", "/feed/"]):
                continue
            seen.add(link)

            title_m = re.search(r'<h[1-4][^>]*class=["\']?[^"\'>]*entry-title[^"\'>]*["\']?[^>]*>\s*<a[^>]*>(.*?)</a>', art, re.DOTALL)
            raw_title = title_m.group(1) if title_m else m_link.group(2)
            title = re.sub(r"<[^>]+>", " ", raw_title).strip()
            title = " ".join(title.split())
            if not title or len(title) < 3:
                continue

            img_m = re.search(r'<img[^>]+(?:data-src|data-lazy-src|src)=["\'](https?://[^"\']+)["\']', art)
            poster = img_m.group(1) if img_m else None

            year_match = re.search(r"\b(19\d\d|20\d\d)\b", title)
            year = int(year_match.group(1)) if year_match else None
            is_series = "season" in title.lower() or "s0" in title.lower() or "series" in title.lower()
            results.append({
                "provider": provider_key,
                "title": title,
                "id": link,
                "type": "Series" if is_series else "Movie",
                "year": year,
                "poster": poster,
            })

    if not results:
        entries = re.findall(r'<a[^>]+href=["\'](https?://[^"\']+)["\'][^>]*title=["\']([^"\']+)["\']', html)
        for link, raw_title in entries:
            if link in seen or any(bad in link for bad in ["/category/", "/tag/", "/page/", "/author/", "/wp-content/", "/feed/"]):
                continue
            seen.add(link)
            title = re.sub(r"<[^>]+>", " ", raw_title).strip()
            title = " ".join(title.split())
            if not title or len(title) < 3:
                continue
            year_match = re.search(r"\b(19\d\d|20\d\d)\b", title)
            year = int(year_match.group(1)) if year_match else None
            is_series = "season" in title.lower() or "s0" in title.lower() or "series" in title.lower()
            results.append({
                "provider": provider_key,
                "title": title,
                "id": link,
                "type": "Series" if is_series else "Movie",
                "year": year,
                "poster": None,
            })
    return results

def search_custom_provider(prov: str, query: str) -> list:
    if prov == "ottstream":
        return search_ott_stream(query)
    domain = get_domain(prov)
    if not domain:
        return []
    if prov in ("vegamovies", "rogmovies"):
        ts_res = search_ts_backend(prov, domain, query)
        wp_res = search_wordpress(prov, domain, query)
        seen = set()
        combined = []
        for r in (ts_res + wp_res):
            if r["id"] not in seen:
                seen.add(r["id"])
                combined.append(r)
        return combined
    elif prov in ("katmovieshd", "hdhub4u"):
        return search_wordpress(prov, domain, query)
    return []

def simplify_language(raw_lang: str) -> str:
    l_low = raw_lang.lower()
    if "hindi" in l_low and any(e in l_low for e in ["eng", "dual", "multi"]):
        return "Hindi + English (Dual Audio)"
    elif "hindi" in l_low:
        return "Hindi Dubbed"
    elif "eng" in l_low:
        return "English"
    elif "tamil" in l_low:
        return "Tamil"
    elif "telugu" in l_low:
        return "Telugu"
    elif "malayalam" in l_low:
        return "Malayalam"
    elif "kannada" in l_low:
        return "Kannada"
    return "Hindi + English (Dual Audio)"

def get_custom_details(prov: str, post_url: str) -> dict:
    if prov == "ottstream":
        return get_ott_details(post_url)
    html = fetch_html(post_url)
    if not html:
        return {"error": "Failed to load page content."}
    
    title_m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
    page_title = title_m.group(1).replace(" - VegaMovies", "").replace(" - RogMovies", "").strip() if title_m else "Movie"
    
    poster_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    poster = poster_m.group(1) if poster_m else None

    # Find all download links with their surrounding HTML context
    link_matches = list(re.finditer(r'href=["\'](https?://[^"\']+)["\']', html))
    all_streams = []
    seen_urls = set()

    for m in link_matches:
        url = m.group(1)
        url_lower = url.lower()
        if not any(k in url_lower for k in ["nexdrive", "hubcloud", "hubdrive", "greenmotors", "playdrive", "fastdl", "vcloud", "gofile", "megaup"]):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        pos = m.start()
        context = html[max(0, pos - 600):pos]
        clean_context = re.sub(r'<[^>]+>', ' ', context)
        clean_context = " ".join(clean_context.split())

        # Extract resolution: pick the LAST occurrence in clean context before the link
        res = 720
        res_matches = list(re.finditer(r'\b(2160|1080|720|480)p?\b|\b(4k)\b', clean_context, re.IGNORECASE))
        if res_matches:
            val = res_matches[-1].group(1) or res_matches[-1].group(2)
            res = 2160 if val.lower() == "4k" else int(val)

        # Extract file size
        size_str = ""
        size_matches = list(re.finditer(r'\b(\d+(?:\.\d+)?\s*(?:MB|GB)(?:/E)?)\b', clean_context, re.IGNORECASE))
        if size_matches:
            size_str = size_matches[-1].group(1).strip("[]")

        # Extract language from context near resolution
        near_text = clean_context[max(0, len(clean_context) - 200):]
        near_low = near_text.lower()
        if "hindi" in near_low and any(k in near_low for k in ["eng", "dual", "multi"]):
            lang = "Hindi + English (Dual Audio)"
        elif "hindi" in near_low:
            lang = "Hindi Dubbed"
        elif "english" in near_low or "eng" in near_low:
            lang = "English"
        elif "tamil" in near_low:
            lang = "Tamil"
        elif "telugu" in near_low:
            lang = "Telugu"
        elif "malayalam" in near_low:
            lang = "Malayalam"
        elif "kannada" in near_low:
            lang = "Kannada"
        else:
            lang = "Hindi + English (Dual Audio)"

        # Mirror label
        lbl = "PlayDrive" if "playdrive" in url_lower else ("V-Cloud" if "vcloud" in url_lower else ("FastDL" if "fastdl" in url_lower else ("HubCloud" if "hubcloud" in url_lower else "Cloud DL")))

        all_streams.append({
            "quality": f"{res}p",
            "resolution": res,
            "language": lang,
            "size": size_str,
            "size_str": size_str,
            "url": url,
            "mirror": lbl,
            "format": "mp4",
        })

    # Group streams by language to create Dubs / Audio selection if multiple languages exist
    lang_groups = {}
    for st in all_streams:
        lang_groups.setdefault(st["language"], []).append(st)

    dubs = []
    if len(lang_groups) > 1:
        for idx, (lang_name, l_streams) in enumerate(lang_groups.items()):
            l_streams.sort(key=lambda s: s.get("resolution", 0), reverse=True)
            dubs.append({
                "id": f"custom_dub_{idx}",
                "language": lang_name,
                "label": lang_name,
                "streams": l_streams,
            })
        final_streams = []
    else:
        all_streams.sort(key=lambda s: s.get("resolution", 0), reverse=True)
        final_streams = all_streams[:15]

    return {
        "title": page_title,
        "type": "Movie",
        "poster": poster,
        "streams": final_streams,
        "dubs": dubs,
        "seasons": [],
        "captions": [],
    }

def rot13(s: str) -> str:
    return s.translate(str.maketrans("ABCDEFGHIJKLMabcdefghijklmNOPQRSTUVWXYZnopqrstuvwxyz", "NOPQRSTUVWXYZnopqrstuvwxyzABCDEFGHIJKLMabcdefghijklm"))

def decode_greenmotors(html: str):
    m = re.search(r"s\(\s*[\x27\"]o[\x27\"]\s*,\s*[\x27\"]([^\x27\"]+)[\x27\"]", html)
    if not m:
        return None
    try:
        p = m.group(1)
        s1 = base64.b64decode(p).decode("utf-8")
        s2 = base64.b64decode(s1).decode("utf-8")
        s3 = rot13(s2)
        s4 = base64.b64decode(s3).decode("utf-8")
        data = json.loads(s4)
        target_b64 = data.get("o", "")
        return base64.b64decode(target_b64).decode("utf-8")
    except Exception as exc:
        logger.warning("decode_greenmotors error: %s", exc)
        return None

def resolve_hubcloud(hubcloud_url: str) -> str:
    html = fetch_html(hubcloud_url)
    if not html:
        return hubcloud_url
    res_link = None
    m_dl = re.search(r"href=[\x27\"](https?://[^\x27\"]*(?:gamerxyt\.com|hubcloud\.php)[^\x27\"]*)[\x27\"]", html)
    if m_dl:
        res_link = m_dl.group(1)
    else:
        m_btn = re.search(r"<a[^>]+id=[\x27\"]download[\x27\"][^>]+href=[\x27\"](https?://[^\x27\"]+)[\x27\"]", html)
        if m_btn:
            res_link = m_btn.group(1)

    if not res_link:
        return hubcloud_url

    r_html = fetch_html(res_link)
    if not r_html:
        return hubcloud_url

    # 1. Cloudflare R2 direct stream
    r2 = re.findall(r"href=[\x27\"](https?://[^\x27\"]*r2\.cloudflarestorage\.com[^\x27\"]+)[\x27\"]", r_html)
    if r2:
        return r2[0]

    # 2. Watch Online pages.dev unwrapped stream
    m_wo = re.search(r"href=[\x27\"](https?://[^\x27\"]*pages\.dev/\?u=([^\x27\"&]+)[^\x27\"]*)[\x27\"]", r_html)
    if m_wo:
        try:
            dec = base64.b64decode(m_wo.group(2)).decode("utf-8")
            if dec.startswith("http"):
                return dec
        except Exception:
            pass

    # 3. PixelDrain API direct stream
    m_px = re.search(r"href=[\x27\"]https?://pixeldrain\.(?:dev|com)/u/([a-zA-Z0-9_-]+)[\x27\"]", r_html)
    if m_px:
        return f"https://pixeldrain.com/api/file/{m_px.group(1)}"

    # 4. 10Gbps direct stream
    m_10g = re.search(r"href=[\x27\"](https?://gpdl\.hubcloud[^\x27\"]+)[\x27\"]", r_html)
    if m_10g:
        return m_10g.group(1)

    return hubcloud_url

def resolve_direct_stream(url: str) -> str:
    u = (url or "").strip()
    u_low = u.lower()

    if "greenmotors" in u_low or "greenmountmotors" in u_low:
        html = fetch_html(u)
        target = decode_greenmotors(html)
        if target:
            if "hubcloud" in target.lower():
                return resolve_hubcloud(target)
            return target

    if "hubcloud" in u_low:
        return resolve_hubcloud(u)

    if "nexdrive" in u_low:
        html = fetch_html(u)
        m = re.search(r"href=[\x27\"](https?://fastdl[^\x27\"]+)[\x27\"]", html)
        if m:
            f_html = fetch_html(m.group(1))
            re_m = re.search(r"var\s+reurl\s*=\s*[\x27\"]([^\x27\"]+)[\x27\"]", f_html)
            if re_m:
                return re_m.group(1)
        for host in ["gofile.io", "megaup.net", "vcloud.my"]:
            m_h = re.search(rf"href=[\x27\"](https?://[^\x27\"]*{host}[^\x27\"]*)[\x27\"]", html)
            if m_h:
                return m_h.group(1)

    if "fastdl" in u_low:
        f_html = fetch_html(u)
        re_m = re.search(r"var\s+reurl\s*=\s*[\x27\"]([^\x27\"]+)[\x27\"]", f_html)
        if re_m:
            return re_m.group(1)

    return u

def search_ott_stream(query: str) -> list:
    query = (query or "").strip()
    if not query:
        return []
    results = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for kind in ["movie", "series"]:
        url = f"https://v3-cinemeta.strem.io/catalog/{kind}/top/search={urllib.parse.quote(query)}.json"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
                for m in data.get("metas", []):
                    title = m.get("name") or ""
                    if not title:
                        continue
                    is_series = (m.get("type") == "series" or kind == "series")
                    results.append({
                        "id": f"ott_{m['id']}_{'series' if is_series else 'movie'}",
                        "title": title,
                        "year": str(m.get("year", "") or ""),
                        "type": "TV Series" if is_series else "Movie",
                        "provider": "ottstream",
                        "poster": m.get("poster") or f"https://images.metahub.space/poster/small/{m['id']}/img",
                        "background": m.get("background") or f"https://images.metahub.space/background/medium/{m['id']}/img"
                    })
        except Exception as e:
            logger.warning("search_ott_stream error for %s: %s", kind, e)

    q_low = query.lower()
    def score_item(it):
        t_low = it["title"].lower()
        score = 0
        if t_low == q_low:
            score += 200
        elif t_low.startswith(q_low):
            score += 100
        elif q_low in t_low:
            score += 50
        if it.get("year"):
            score += 10
        return score

    results.sort(key=score_item, reverse=True)
    return results

def get_ott_details(item_id: str) -> dict:
    parts = item_id.split("_")
    imdb_id = parts[1] if len(parts) >= 2 else item_id
    kind = parts[2] if len(parts) >= 3 else ("series" if "series" in item_id else "movie")
    url = f"https://v3-cinemeta.strem.io/meta/{kind}/{imdb_id}.json"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        meta = data.get("meta", {})
    except Exception as exc:
        logger.warning("get_ott_details error: %s", exc)
        meta = {"name": imdb_id, "id": imdb_id}

    title = meta.get("name") or "OTT Stream"
    poster = meta.get("poster") or f"https://images.metahub.space/poster/small/{imdb_id}/img"
    plot = meta.get("description") or meta.get("overview") or ""
    rating = meta.get("imdbRating") or meta.get("rating")
    duration = meta.get("runtime") or ""
    year = meta.get("year") or ""

    if kind == "series" or meta.get("type") == "series" or meta.get("videos"):
        seasons_dict = {}
        for v in meta.get("videos", []):
            s_num = int(v.get("season", 1))
            if s_num == 0:
                continue
            e_num = int(v.get("number", v.get("episode", 1)))
            seasons_dict.setdefault(s_num, []).append({
                "number": e_num,
                "season": s_num,
                "title": v.get("name") or f"Episode {e_num}",
                "overview": v.get("overview", "")
            })
        if not seasons_dict:
            for v in meta.get("videos", []):
                s_num = int(v.get("season", 0))
                e_num = int(v.get("number", v.get("episode", 1)))
                seasons_dict.setdefault(s_num, []).append({
                    "number": e_num,
                    "season": s_num,
                    "title": v.get("name") or f"Episode {e_num}",
                    "overview": v.get("overview", "")
                })
        seasons = []
        for s_num in sorted(seasons_dict.keys()):
            eps = sorted(seasons_dict[s_num], key=lambda x: x["number"])
            seasons.append({"number": s_num, "episodes": eps})
        return {
            "title": title,
            "year": year,
            "rating": rating,
            "duration": duration,
            "plot": plot,
            "poster": poster,
            "type": "TV Series",
            "provider": "ottstream",
            "seasons": seasons,
            "streams": [],
            "captions": [],
        }

    streams = [
        {"quality": "1080p", "resolution": 1080, "size_str": "Server 1 (Ultra HD Fast)", "language": "Multi-Audio (Hindi/Eng)", "url": f"https://vidsrc.su/embed/movie/{imdb_id}", "format": "hls"},
        {"quality": "1080p", "resolution": 1080, "size_str": "Server 2 (Cloud Player)", "language": "English / Dual", "url": f"https://www.2embed.cc/embed/{imdb_id}", "format": "hls"},
        {"quality": "1080p", "resolution": 1080, "size_str": "Server 3 (Backup HD)", "language": "Multi", "url": f"https://autoembed.to/movie/imdb/{imdb_id}", "format": "hls"},
    ]
    return {
        "title": title,
        "year": year,
        "rating": rating,
        "duration": duration,
        "plot": plot,
        "poster": poster,
        "type": "Movie",
        "provider": "ottstream",
        "streams": streams,
        "dubs": [],
        "seasons": [],
        "captions": [],
    }

def get_ott_episode_streams(item_id: str, season: int, episode: int) -> dict:
    parts = item_id.split("_")
    imdb_id = parts[1] if len(parts) >= 2 else item_id
    streams = [
        {"quality": "1080p", "resolution": 1080, "size_str": "Server 1 (Ultra HD Fast)", "language": "Multi-Audio (Hindi/Eng)", "url": f"https://vidsrc.su/embed/tv/{imdb_id}/{season}/{episode}", "format": "hls"},
        {"quality": "1080p", "resolution": 1080, "size_str": "Server 2 (Cloud Player)", "language": "English / Dual", "url": f"https://www.2embed.cc/embedtv/{imdb_id}&s={season}&e={episode}", "format": "hls"},
        {"quality": "1080p", "resolution": 1080, "size_str": "Server 3 (Backup HD)", "language": "Multi-Sub", "url": f"https://autoembed.to/tv/imdb/{imdb_id}-{season}-{episode}", "format": "hls"},
    ]
    return {"streams": streams, "captions": []}
