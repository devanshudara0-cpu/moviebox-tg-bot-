import asyncio
import html.parser
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

STANDARD_QUALITIES = (360, 480, 720, 1080, 1440, 2160)


def normalize_url(raw_url: str) -> str:
    """Validate and normalize an HTTP/HTTPS URL, preserving path and sorted query params."""
    raw_url = raw_url.strip()
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid HTTP(S) URL: {raw_url!r}")
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if (scheme == "http" and netloc.endswith(":80")) or (scheme == "https" and netloc.endswith(":443")):
        netloc = netloc.rsplit(":", 1)[0]
    path = re.sub(r"/{2,}", "/", parsed.path) or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunparse((scheme, netloc, path, "", query, ""))


def label_resolution(height: Optional[int]) -> str:
    """Map numeric video height to standard quality label without fabricating missing values."""
    if not height or height <= 0:
        return "Unknown"
    if height >= 2160:
        return "2160p (4K)"
    closest = min(STANDARD_QUALITIES, key=lambda q: abs(q - height))
    if abs(closest - height) <= 60:
        return f"{closest}p"
    return f"{height}p"


@dataclass
class StreamVariant:
    url: str
    format: str  # "mp4", "hls", "dash"
    height: Optional[int] = None
    width: Optional[int] = None
    bandwidth: Optional[int] = None
    quality: str = "Unknown"


@dataclass
class MediaInspection:
    original_url: str
    final_url: str
    redirect_chain: List[Tuple[int, str]] = field(default_factory=list)
    content_type: str = ""
    title: Optional[str] = None
    og_image: Optional[str] = None
    variants: List[StreamVariant] = field(default_factory=list)
    error: Optional[str] = None


class _MetaHTMLParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: Dict[str, str] = {}
        self._in_title = False
        self.title_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").lower()
            if key and attr_map.get("content"):
                self.meta[key] = attr_map["content"].strip()
        elif tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


def extract_html_metadata(html_text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract title, og:image, and og:video from HTML."""
    parser = _MetaHTMLParser()
    parser.feed(html_text)
    title = parser.meta.get("og:title") or "".join(parser.title_parts).strip() or None
    image = parser.meta.get("og:image") or None
    video = parser.meta.get("og:video:secure_url") or parser.meta.get("og:video") or None
    return title, image, video


def parse_m3u8(playlist_text: str, base_url: str) -> List[StreamVariant]:
    """Parse an HLS master playlist and return discovered stream variants."""
    variants: List[StreamVariant] = []
    lines = [ln.strip() for ln in playlist_text.splitlines() if ln.strip()]
    for idx, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF:"):
            attrs = line.split(":", 1)[1]
            res_match = re.search(r"RESOLUTION=(\d+)x(\d+)", attrs)
            bw_match = re.search(r"BANDWIDTH=(\d+)", attrs)
            width = int(res_match.group(1)) if res_match else None
            height = int(res_match.group(2)) if res_match else None
            bw = int(bw_match.group(1)) if bw_match else None
            if idx + 1 < len(lines) and not lines[idx + 1].startswith("#"):
                stream_url = urljoin(base_url, lines[idx + 1])
                variants.append(
                    StreamVariant(
                        url=stream_url,
                        format="hls",
                        height=height,
                        width=width,
                        bandwidth=bw,
                        quality=label_resolution(height),
                    )
                )
    variants.sort(key=lambda v: (v.height or 0, v.bandwidth or 0), reverse=True)
    return variants
    def parse_mpd(mpd_xml: str, manifest_url: str) -> List[StreamVariant]:
    """Parse a DASH MPD manifest and return discovered video representations."""
    variants: List[StreamVariant] = []
    root = ET.fromstring(mpd_xml)
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag == "Representation":
            mime = (elem.attrib.get("mimeType") or "").lower()
            height_str = elem.attrib.get("height")
            width_str = elem.attrib.get("width")
            bw_str = elem.attrib.get("bandwidth")
            if mime.startswith("audio") and not height_str:
                continue
            height = int(height_str) if height_str and height_str.isdigit() else None
            width = int(width_str) if width_str and width_str.isdigit() else None
            bw = int(bw_str) if bw_str and bw_str.isdigit() else None
            if height or mime.startswith("video"):
                variants.append(
                    StreamVariant(
                        url=manifest_url,
                        format="dash",
                        height=height,
                        width=width,
                        bandwidth=bw,
                        quality=label_resolution(height),
                    )
                )
    variants.sort(key=lambda v: (v.height or 0, v.bandwidth or 0), reverse=True)
    return variants


class AsyncMediaClient:
    """Async HTTPX client with retry handling and explicit redirect-chain inspection."""

    def __init__(
        self,
        timeout: float = 15.0,
        max_retries: int = 2,
        max_redirects: int = 5,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_redirects = max_redirects
        self._transport = transport

    async def _request_with_retry(self, client: httpx.AsyncClient, method: str, url: str) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                return await client.request(method, url, follow_redirects=False)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = exc
                logger.warning("Attempt %d failed for %s: %s", attempt + 1, url, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(0.2 * (attempt + 1))
        raise RuntimeError(f"Request failed after {self.max_retries + 1} attempts: {last_exc}")

    async def inspect(self, raw_url: str) -> MediaInspection:
        normalized = normalize_url(raw_url)
        chain: List[Tuple[int, str]] = []
        current = normalized

        async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
            resp: Optional[httpx.Response] = None
            for _ in range(self.max_redirects + 1):
                resp = await self._request_with_retry(client, "GET", current)
                if resp.is_redirect and "location" in resp.headers:
                    chain.append((resp.status_code, current))
                    current = normalize_url(urljoin(current, resp.headers["location"]))
                else:
                    break
            else:
                return MediaInspection(
                    original_url=normalized,
                    final_url=current,
                    redirect_chain=chain,
                    error="Exceeded max redirects",
                )

            assert resp is not None
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            result = MediaInspection(
                original_url=normalized,
                final_url=current,
                redirect_chain=chain,
                content_type=ctype,
            )

            if resp.status_code >= 400:
                result.error = f"HTTP {resp.status_code}"
                return result

            if ctype.startswith("video/mp4") or current.lower().endswith(".mp4"):
                result.variants = [StreamVariant(url=current, format="mp4", quality="Direct MP4")]
            elif "mpegurl" in ctype or current.lower().endswith(".m3u8"):
                result.variants = parse_m3u8(resp.text, current)
            elif "dash+xml" in ctype or current.lower().endswith(".mpd"):
                result.variants = parse_mpd(resp.text, current)
            elif "html" in ctype:
                title, img, og_vid = extract_html_metadata(resp.text)
                result.title = title
                result.og_image = img
                if og_vid:
                    vid_url = normalize_url(urljoin(current, og_vid))
                    fmt = "hls" if ".m3u8" in vid_url else ("dash" if ".mpd" in vid_url else "mp4")
                    result.variants = [StreamVariant(url=vid_url, format=fmt, quality=f"OG {fmt.upper()}")]
            return result


class SessionStore:
    """Isolated per-user session state for Telegram inline workflows."""

    def __init__(self) -> None:
        self._data: Dict[int, Dict] = {}

    def set(self, user_id: int, key: str, value: object) -> None:
        self._data.setdefault(user_id, {})[key] = value

    def get(self, user_id: int, key: str, default: object = None) -> object:
        return self._data.get(user_id, {}).get(key, default)

    def clear(self, user_id: int) -> None:
        self._data.pop(user_id, None)
  
