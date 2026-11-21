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

def extract_resolution(text: str) -> int:
    m = re.search(r"\b(2160|1080|720|480)p?\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 720

def get_custom_details(prov: str, post_url: str) -> dict:
    html = fetch_html(post_url)
    if not html:
        return {"error": "Failed to load page content."}
    
    title_m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
    page_title = title_m.group(1).replace(" - VegaMovies", "").replace(" - RogMovies", "").strip() if title_m else "Movie"
    
    poster_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    poster = poster_m.group(1) if poster_m else None

    streams = []
    seen_urls = set()

    a_tags = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL)
    for href, raw_btn in a_tags:
        btn_text = re.sub(r'<[^>]+>', '', raw_btn).strip()
        lower_href = href.lower()
        if "playdrive" in lower_href:
            streams.append({
                "quality": "Direct Stream (PlayDrive)",
                "resolution": 1080,
                "url": href,
                "mirror": "PlayDrive",
                "format": "mp4",
            })
            continue

        if "nexdrive" in lower_href:
            nex_html = fetch_html(href, timeout=8)
            if nex_html:
                sub_links = re.findall(r'href=["\']([^"\']+)["\']', nex_html)
                for sl in sub_links:
                    if sl in seen_urls:
                        continue
                    sl_lower = sl.lower()
                    if any(k in sl_lower for k in ["fastdl", "vcloud", "gofile", "megaup", "filebee", "vikingfile"]):
                        seen_urls.add(sl)
                        lbl = "FastDL" if "fastdl" in sl_lower else ("V-Cloud" if "vcloud" in sl_lower else "Cloud DL")
                        res = extract_resolution(btn_text + " " + sl)
                        streams.append({
                            "quality": f"{res}p [{lbl}]",
                            "resolution": res,
                            "url": sl,
                            "mirror": lbl,
                            "format": "mp4",
                        })

        if any(k in lower_href for k in ["hubcloud", "hubdrive", "fastdl", "vcloud", "gofile"]):
            if href not in seen_urls:
                seen_urls.add(href)
                res = extract_resolution(btn_text + " " + href)
                lbl = "HubCloud" if "hubcloud" in lower_href else ("FastDL" if "fastdl" in lower_href else "Cloud DL")
                streams.append({
                    "quality": f"{res}p [{lbl}]",
                    "resolution": res,
                    "url": href,
                    "mirror": lbl,
                    "format": "mp4",
                })

    streams.sort(key=lambda s: s.get("resolution", 0), reverse=True)
    return {
        "title": page_title,
        "type": "Movie",
        "poster": poster,
        "streams": streams[:15],
        "dubs": [],
        "seasons": [],
        "captions": [],
    }
