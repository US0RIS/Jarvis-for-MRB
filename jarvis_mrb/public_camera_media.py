from __future__ import annotations

"""User-selected public HTTPS camera media, not a camera crawler or scanner.

No credentials, private IPs, arbitrary redirect, proxy, HTTP/RTSP, hidden
web-page parsing, remote ffmpeg URL opening or persisted frame buffers.
DNS is checked on EVERY request and the vetted public address is the actual
socket destination (TLS verification still uses the requested host).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import io
import os
import re
import shutil
import socket
import ssl
import subprocess
from typing import Any
from urllib.parse import urljoin, urlsplit

from PIL import Image, UnidentifiedImageError

_MAX_URL = 1800
_MAX_IMAGE = 3_000_000
_MAX_PLAYLIST = 180_000
_MAX_SEGMENT = 2_500_000
_MAX_TS = 7_500_000
_IMAGE_TYPES = ("image/jpeg", "image/jpg", "image/png", "image/webp")
_HLS_TYPES = ("application/vnd.apple.mpegurl", "application/x-mpegurl")
_AUTH_QUERY = re.compile(
    r"(?:^|[&;])(?:token|key|password|pass|auth|api_key|apikey|"
    r"access_token|sig|signature|session|secret)=", re.I
)


@dataclass(frozen=True)
class MediaTarget:
    url: str
    host: str
    display: str
    id: str


def validate_public_camera_url(
    url: str, *, provider_signed: bool = False, allow_http: bool = False,
) -> MediaTarget:
    """Validate syntax, not DNS. Network checks occur on each actual fetch."""
    if type(url) is not str or len(url) > _MAX_URL:
        raise ValueError("Public camera URL must be an HTTPS media URL under 1800 characters.")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if (scheme not in (("https", "http") if allow_http else ("https",))
            or (scheme == "http" and provider_signed)
            or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.fragment or any(ord(x) < 33 for x in url)):
        raise ValueError("Only explicit public HTTPS media URLs are supported.")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Invalid camera URL port.") from exc
    if port not in (None, 80 if scheme == "http" else 443):
        raise ValueError("Camera URL must use the standard protocol port.")
    hostname = parts.hostname.lower().rstrip(".")
    if (not hostname or len(hostname) > 253 or "." not in hostname
            or hostname.endswith((".local", ".internal", ".localhost", ".onion"))
            or not re.fullmatch(r"[a-z0-9.-]+", hostname)
            or hostname.startswith("localhost")):
        raise ValueError("Camera needs a public DNS hostname.")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("Literal IP camera hosts are not supported.")
    if not provider_signed and _AUTH_QUERY.search(parts.query):
        raise ValueError("Credential/signed camera URLs cannot be saved; use a provider adapter.")
    # Do not include query parameters or signed credentials in metadata.
    display = scheme + "://" + hostname + (parts.path or "/")
    identifier = hashlib.sha256(url.encode()).hexdigest()
    return MediaTarget(url, hostname, display[:350], identifier)


def _public_address(host: str, port: int = 443) -> str:
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("Camera DNS lookup unavailable.") from exc
    addresses = sorted({x[4][0] for x in answers})
    if not addresses:
        raise ValueError("Camera has no public DNS addresses.")
    if any(not ipaddress.ip_address(x).is_global for x in addresses):
        raise ValueError("Camera DNS resolves to a non-public address.")
    return addresses[0]


class _PinnedTLS(http.client.HTTPSConnection):
    """Connect to the resolved vetted IP; retain real-host SNI/cert validation."""
    def __init__(self, target: MediaTarget, ip: str):
        super().__init__(target.host, port=443, timeout=12,
                         context=ssl.create_default_context())
        self._public_ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._public_ip, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


class _PinnedPlainHTTP(http.client.HTTPConnection):
    """Operator-selected HTTP media only; still pinned to verified public IP."""
    def __init__(self, target: MediaTarget, ip: str):
        super().__init__(target.host, port=80, timeout=12)
        self._public_ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._public_ip, 80), self.timeout)


def _get(target: MediaTarget, *, limit: int, accept: str,
         provider_signed: bool = False,
         allow_http: bool = False) -> tuple[bytes, str]:
    # Validate again for each playlist/segment GET, including relative URLs.
    target = validate_public_camera_url(
        target.url, provider_signed=provider_signed, allow_http=allow_http
    )
    scheme = urlsplit(target.url).scheme.lower()
    port = 80 if scheme == "http" else 443
    ip = _public_address(target.host, port) if port == 80 else _public_address(target.host)
    con = (_PinnedPlainHTTP(target, ip) if port == 80 else _PinnedTLS(target, ip))
    try:
        parts = urlsplit(target.url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        con.request("GET", path, headers={
            "Host": target.host, "Accept": accept,
            "User-Agent": "JarvisCamera/1.0 (single public still; opt-in)",
            "Connection": "close",
        })
        response = con.getresponse()
        if response.status != 200:
            # Avoid reflecting private query strings/headers in error messages.
            raise ValueError("Camera endpoint unavailable or access restricted.")
        mime = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        if response.getheader("Content-Length"):
            try:
                length = int(response.getheader("Content-Length", "0"))
                if length > limit:
                    raise ValueError("Camera response exceeds the byte budget.")
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ValueError) and "budget" in str(exc):
                    raise
                raise ValueError("Invalid camera response size.") from exc
        data = bytearray()
        while len(data) <= limit:
            chunk = response.read(min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if b"\xff\xd9" in data and mime.startswith("multipart/"):
                # One complete JPEG is enough; never record a stream.
                break
        if len(data) > limit:
            raise ValueError("Camera response exceeds the byte budget.")
        return bytes(data), mime
    finally:
        con.close()


def _image(data: bytes, mime: str) -> tuple[bytes, str]:
    if mime.startswith("multipart/"):
        start = data.find(b"\xff\xd8\xff")
        end = data.find(b"\xff\xd9", start + 3)
        if start < 0 or end < 0:
            raise ValueError("MJPEG stream has no complete JPEG within budget.")
        data, mime = data[start:end + 2], "image/jpeg"
    signature = (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    )
    if mime not in _IMAGE_TYPES or not signature:
        raise ValueError("Camera did not return an actual JPEG, PNG or WebP still.")
    if len(data) > _MAX_IMAGE:
        raise ValueError("Image exceeds camera byte limit.")
    # PIL fails closed on spoofed MIME, malformed or decompression-bomb input.
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > 12_000_000:
                raise ValueError("Image dimensions exceed bounded vision input.")
            rgb = im.convert("RGB")
            out = io.BytesIO()
            rgb.save(out, format="JPEG", quality=83)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Camera media is not a decodable public image.") from exc
    if out.tell() > _MAX_IMAGE:
        raise ValueError("Decoded image exceeds bounded vision input.")
    return out.getvalue(), "jpeg"


def _hls_media(url: MediaTarget, manifest: bytes, *, signed: bool,
               depth: int = 0, allow_http: bool = False) -> bytes:
    if depth > 1 or len(manifest) > _MAX_PLAYLIST:
        raise ValueError("Unsupported nested or oversized HLS manifest.")
    try:
        content = manifest.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Invalid HLS manifest encoding.") from exc
    lines = [x.strip() for x in content.splitlines() if x.strip()]
    if not lines or lines[0] != "#EXTM3U":
        raise ValueError("Not a supported HLS playlist.")
    if any(x.startswith(("#EXT-X-KEY", "#EXT-X-MAP", "#EXT-X-BYTERANGE",
                         "#EXT-X-I-FRAME-STREAM-INF")) for x in lines):
        raise ValueError("Encrypted, fMP4 and byte-range HLS require a vetted provider adapter.")
    if any(x.startswith("#EXT-X-STREAM-INF") for x in lines):
        candidates = [x for x in lines if not x.startswith("#")]
        if not candidates:
            raise ValueError("HLS master playlist has no media variant.")
        item = _same_origin(url, candidates[0], signed=signed,
                            allow_http=allow_http)
        child, mime = _get(item, limit=_MAX_PLAYLIST,
                           accept="application/vnd.apple.mpegurl",
                           provider_signed=signed, allow_http=allow_http)
        if mime not in _HLS_TYPES and not item.url.split("?", 1)[0].endswith(".m3u8"):
            raise ValueError("HLS variant has unexpected content type.")
        return _hls_media(item, child, signed=signed, depth=depth + 1,
                          allow_http=allow_http)
    segments = [x for x in lines if not x.startswith("#")]
    if not segments or len(segments) > 250:
        raise ValueError("HLS playlist has no bounded segments.")
    # Latest two full MPEG-TS chunks; never fetch other hosts, keys or pages.
    ts = bytearray()
    for segment in segments[-2:]:
        item = _same_origin(url, segment, signed=signed,
                            allow_http=allow_http)
        if not item.url.split("?", 1)[0].lower().endswith(".ts"):
            raise ValueError("Only unencrypted MPEG-TS HLS is supported.")
        data, mime = _get(item, limit=_MAX_SEGMENT,
                          accept="video/mp2t", provider_signed=signed,
                          allow_http=allow_http)
        ts.extend(data)
    if not ts or len(ts) > _MAX_TS:
        raise ValueError("HLS segment budget exceeded.")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("This public HLS camera requires locally installed FFmpeg.")
    try:
        result = subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-protocol_whitelist", "pipe", "-f", "mpegts", "-i", "pipe:0",
            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg",
            "pipe:1",
        ], input=bytes(ts), capture_output=True, timeout=9, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Local HLS frame decoder unavailable.") from exc
    if result.returncode or len(result.stdout) > _MAX_IMAGE:
        raise ValueError("Local HLS frame could not be decoded within budget.")
    return result.stdout


def _same_origin(base: MediaTarget, relative: str, *, signed: bool,
                 allow_http: bool = False) -> MediaTarget:
    if len(relative) > _MAX_URL or relative.startswith(("//", "\\\\")):
        raise ValueError("HLS cross-origin or oversized reference rejected.")
    result = validate_public_camera_url(
        urljoin(base.url, relative), provider_signed=signed,
        allow_http=allow_http,
    )
    if (result.host != base.host
            or urlsplit(result.url).scheme != urlsplit(base.url).scheme):
        raise ValueError("HLS media must remain on the enrolled host.")
    return result


def snapshot_public_media(
    url: str, *, provider_signed: bool = False, allow_http: bool = False,
) -> dict[str, Any]:
    """Inspect one explicitly selected public frame; never store raw imagery."""
    target = validate_public_camera_url(
        url, provider_signed=provider_signed, allow_http=allow_http
    )
    raw, mime = _get(target, limit=_MAX_IMAGE + 1,
                     accept="image/jpeg,image/png,image/webp,multipart/x-mixed-replace,"
                            "application/vnd.apple.mpegurl,application/x-mpegurl",
                     provider_signed=provider_signed, allow_http=allow_http)
    media_kind = "published_still"
    if mime in _HLS_TYPES or target.url.split("?", 1)[0].endswith(".m3u8"):
        raw = _hls_media(
            target, raw, signed=provider_signed, allow_http=allow_http
        )
        mime = "image/jpeg"
        media_kind = "hls_one_decoded_frame"
    elif mime.startswith("multipart/"):
        media_kind = "mjpeg_one_frame"
    frame, _ = _image(raw, mime)
    return {
        "frame": frame,
        "sha256": hashlib.sha256(frame).hexdigest(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "capture_time": None,
        "source_display": target.display,
        "source_id": target.id,
        "media_kind": media_kind,
        "bytes": len(frame),
    }


def discover_public_page_media(page_url: str) -> dict[str, Any]:
    """One bounded read of an explicitly chosen public HTML page.

    This does not execute JavaScript, follow embeds, search hosts, or fetch
    candidate media. The operator chooses a direct media URL afterward.
    """
    from html.parser import HTMLParser

    page = validate_public_camera_url(page_url)
    body, mime = _get(
        page, limit=180_000, accept="text/html,application/xhtml+xml",
    )
    if mime in _IMAGE_TYPES or mime.startswith("multipart/") or mime in _HLS_TYPES:
        return {
            "status": "direct_media",
            "candidates": [{
                "url": page.url, "source": "exact_user_selected_media",
                "same_origin": True,
                "needs_explicit_selection": True,
            }],
            "qualifier": "This address is already published media.",
        }
    if mime not in ("text/html", "application/xhtml+xml"):
        raise ValueError("This page does not expose supported public HTML/media.")
    try:
        html = body.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Unsupported public page encoding.") from exc

    class CandidateParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.found: list[tuple[str, str]] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if len(self.found) >= 50:
                return
            values = dict(attrs)
            if tag == "meta" and str(values.get("property") or "").lower() in {
                "og:image", "twitter:image",
            }:
                self.found.append((values.get("content") or "", "public_page_thumbnail"))
            elif tag in {"img", "source", "video"}:
                candidate = values.get("src") or values.get("data-src") or ""
                meta = " ".join(str(values.get(x) or "") for x in (
                    "alt", "id", "class", "type", "title",
                )).lower()
                suffix = candidate.lower().split("?", 1)[0]
                if ("camera" in meta or "webcam" in meta or "live" in meta
                        or "snapshot" in meta or "image/" in meta
                        or suffix.endswith((".m3u8", ".jpg", ".jpeg",
                                            ".png", ".webp"))):
                    self.found.append((candidate, "html_camera_media_candidate"))

    parser = CandidateParser()
    parser.feed(html[:180_000])
    unique: set[str] = set()
    candidates = []
    for relative, source in parser.found:
        if len(candidates) >= 15:
            break
        try:
            candidate = validate_public_camera_url(urljoin(page.url, relative))
        except (ValueError, TypeError):
            continue
        if candidate.url in unique:
            continue
        unique.add(candidate.url)
        candidates.append({
            "url": candidate.url, "source": source,
            "same_origin": candidate.host == page.host,
            "needs_explicit_selection": True,
        })
    return {
        "status": "candidates_found" if candidates else "no_static_media_candidates",
        "candidates": candidates,
        "page_display": page.display,
        "qualifier": (
            "Only literal media links in this selected HTML document were "
            "examined; no JavaScript/player/iframe execution, recording, "
            "private access or external media request. A thumbnail may not "
            "be a live camera image. Choose a specific candidate to inspect."
        ),
    }
