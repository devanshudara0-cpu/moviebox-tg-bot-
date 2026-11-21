import os
import json
import re
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
    "hdhub4u": "https://hdboss.in",
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
    articles = re.findall(r'<article[^>]*>.*?<a[^>]+href=["\'](https?://[^"\']+)["\'][^>]*>(.*?)</a>.*?</article>', html, re.DOTALL)
    seen = set()
    for link, raw_title in articles:
        if link in seen:
            continue
        seen.add(link)
        title = re.sub(r"<[^>]+>", "", raw_title).strip()
        if not title:
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
        })
    return results

def search_custom_provider(prov: str, query: str) -> list:
    domain = get_domain(prov)
    if not domain:
        return []
    if prov in ("vegamovies", "rogmovies"):
        res = search_ts_backend(prov, domain, query)
        if res:
            return res
        return search_wordpress(prov, domain, query)
    elif prov == "katmovieshd":
        return search_wordpress(prov, domain, query)
    elif prov == "hdhub4u":
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
        if not any(k in url_lower for k in ["nexdrive", "hubcloud", "hubdrive", "playdrive", "fastdl", "vcloud", "gofile", "megaup"]):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        pos = m.start()
        context = html[max(0, pos - 350):pos]
        clean_context = re.sub(r'<[^>]+>', ' ', context)
        clean_context = " ".join(clean_context.split())

        # Extract resolution
        res = 720
        res_m = re.search(r'\b(2160|1080|720|480)p?\b|\b(4k)\b', clean_context, re.IGNORECASE)
        if res_m:
            v = res_m.group(1) or res_m.group(2)
            res = 2160 if v.lower() == "4k" else int(v)

        # Extract language
        lang = "Hindi + English (Dual Audio)"
        lang_m = re.search(r'\[([^\]]*?(?:Hindi|English|Dual|Multi|Tamil|Telugu|Dubbed)[^\]]*?)\]|\{([^\}]*?(?:Hindi|English|Dual|Multi|Tamil|Telugu|Dubbed)[^\}]*?)\}|\b(Dual\s+Audio|Hindi\s+Dubbed|Multi\s+Audio)\b', clean_context, re.IGNORECASE)
        if lang_m:
            matched_lang = lang_m.group(1) or lang_m.group(2) or lang_m.group(3)
            lang = simplify_language(matched_lang)

        # Extract file size
        size_str = ""
        size_m = re.search(r'\[(\d+(?:\.\d+)?\s*(?:MB|GB)(?:/E)?)\]', clean_context, re.IGNORECASE)
        if size_m:
            size_str = size_m.group(1)

        # Mirror label
        lbl = "PlayDrive" if "playdrive" in url_lower else ("V-Cloud" if "vcloud" in url_lower else ("FastDL" if "fastdl" in url_lower else ("HubCloud" if "hubcloud" in url_lower else "Cloud DL")))
        
        q_label = f"{res}p" + (f" [{size_str}]" if size_str else "") + f" • {lang}"

        all_streams.append({
            "quality": q_label,
            "resolution": res,
            "language": lang,
            "size": size_str,
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
