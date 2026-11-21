from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse

from media_resolver import AsyncMediaClient, MediaInspection, StreamVariant, normalize_url


@dataclass
class AdapterResult:
    source_url: str
    adapter_name: str
    supported: bool
    variants: List[StreamVariant] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    limitation: Optional[str] = None


class MirrorAdapter:
    """Base interface for Server 2 mirror adapters."""

    name: str = "base"

    def can_handle(self, url: str) -> bool:
        raise NotImplementedError

    async def resolve(self, url: str, client: AsyncMediaClient) -> AdapterResult:
        raise NotImplementedError


class ProtectedMirrorAdapter(MirrorAdapter):
    """
    Adapter for HubCloud, HubDrive, and redirector/verification hosts.
    Inspects public headers/OpenGraph metadata without bypassing verification gates.
    """

    name = "protected_mirror"
    KNOWN_HOSTS = ("hubcloud", "hubdrive", "greenmotors")

    def can_handle(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(k in host for k in self.KNOWN_HOSTS)

    async def resolve(self, url: str, client: AsyncMediaClient) -> AdapterResult:
        insp: MediaInspection = await client.inspect(url)
        meta: Dict[str, str] = {
            "final_url": insp.final_url,
            "content_type": insp.content_type or "unknown",
        }
        if insp.title:
            meta["title"] = insp.title
        if insp.error:
            return AdapterResult(
                source_url=url,
                adapter_name=self.name,
                supported=False,
                metadata=meta,
                limitation=insp.error,
            )

        if insp.variants:
            resolved_variants: List[StreamVariant] = []
            for v in insp.variants:
                if v.format in ("hls", "dash") or v.url != insp.final_url:
                    sub = await client.inspect(v.url)
                    if sub.variants:
                        resolved_variants.extend(sub.variants)
                        continue
                resolved_variants.append(v)
            return AdapterResult(
                source_url=url,
                adapter_name=self.name,
                supported=True,
                variants=resolved_variants,
                metadata=meta,
            )

        return AdapterResult(
            source_url=url,
            adapter_name=self.name,
            supported=False,
            metadata=meta,
            limitation="Protected verification / HTML gate (no documented public API)",
        )


class DirectStreamAdapter(MirrorAdapter):
    """Fallback adapter for accessible direct MP4, HLS (.m3u8), and DASH (.mpd) URLs."""

    name = "direct_stream"

    def can_handle(self, url: str) -> bool:
        scheme = urlparse(url).scheme.lower()
        return scheme in ("http", "https")

    async def resolve(self, url: str, client: AsyncMediaClient) -> AdapterResult:
        insp: MediaInspection = await client.inspect(url)
        meta: Dict[str, str] = {
            "final_url": insp.final_url,
            "content_type": insp.content_type or "unknown",
        }
        if insp.title:
            meta["title"] = insp.title
        if insp.error:
            return AdapterResult(
                source_url=url,
                adapter_name=self.name,
                supported=False,
                metadata=meta,
                limitation=insp.error,
            )
        if not insp.variants:
            return AdapterResult(
                source_url=url,
                adapter_name=self.name,
                supported=False,
                metadata=meta,
                limitation="No playable MP4, HLS, or DASH stream found",
            )
        return AdapterResult(
            source_url=url,
            adapter_name=self.name,
            supported=True,
            variants=insp.variants,
            metadata=meta,
        )


class AdapterRegistry:
    """Routes Server 2 mirror URLs to the first matching adapter."""

    def __init__(self, adapters: Optional[List[MirrorAdapter]] = None) -> None:
        self.adapters: List[MirrorAdapter] = adapters or [
            ProtectedMirrorAdapter(),
            DirectStreamAdapter(),
        ]

    async def resolve(self, raw_url: str, client: AsyncMediaClient) -> AdapterResult:
        normalized = normalize_url(raw_url)
        for adapter in self.adapters:
            if adapter.can_handle(normalized):
                return await adapter.resolve(normalized, client)
        return AdapterResult(
            source_url=normalized,
            adapter_name="none",
            supported=False,
            limitation="No matching adapter for URL",
        )
