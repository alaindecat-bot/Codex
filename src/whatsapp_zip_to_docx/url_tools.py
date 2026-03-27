from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import json
import mimetypes
from pathlib import Path
import re
import subprocess
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

TITLE_RE = re.compile(r"<title>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)


@dataclass
class UrlInfo:
    original_url: str
    final_url: str
    domain: str
    content_type: Optional[str]
    status: Optional[int]
    page_title: Optional[str] = None
    og_title: Optional[str] = None
    og_description: Optional[str] = None
    og_type: Optional[str] = None
    og_image: Optional[str] = None
    og_site_name: Optional[str] = None
    author: Optional[str] = None
    image_fetchable: Optional[bool] = None
    error: Optional[str] = None

    @property
    def kind(self) -> str:
        domain = self.domain.lower()
        content_type = (self.content_type or "").lower()
        if "spotify.com" in domain:
            return "spotify"
        if "facebook.com" in domain or "fb.watch" in domain:
            return "facebook"
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
        if content_type.startswith("audio/"):
            return "audio"
        if self.error:
            return "unreachable"
        return "webpage"

    @property
    def lyrics_searchable(self) -> Optional[bool]:
        if self.kind != "spotify":
            return None
        if (self.og_type or "").lower() == "music.song" and (self.og_title or self.page_title):
            return True
        return False

    @property
    def can_embed_post_image(self) -> Optional[bool]:
        if self.kind != "facebook":
            return None
        return bool(self.og_image and self.image_fetchable)

    @property
    def spotify_artists(self) -> Optional[str]:
        if self.kind != "spotify" or not self.og_description:
            return None
        parts = [part.strip() for part in self.og_description.split("·")]
        if parts:
            return parts[0] or None
        return None

    @property
    def facebook_content_type(self) -> Optional[str]:
        if self.kind != "facebook":
            return None
        og_type = (self.og_type or "").lower()
        if "video" in og_type:
            return "video"
        if "article" in og_type:
            return "article"
        if og_type:
            return "post"
        return None

    @property
    def facebook_source(self) -> Optional[str]:
        if self.kind != "facebook":
            return None
        if self.og_site_name:
            return self.og_site_name
        title = (self.og_title or "").strip()
        if not title:
            return None
        if " | " in title:
            return title.split(" | ")[-1].strip() or title
        if " · " in title:
            return title.split(" · ")[-1].strip() or title
        return title

    @property
    def facebook_summary(self) -> Optional[str]:
        if self.kind != "facebook":
            return None
        description = (self.og_description or "").strip()
        title = (self.og_title or "").strip()
        if not description:
            return None
        if description == title:
            return None
        if title and title in description and len(description) - len(title) < 20:
            return None
        return description

    @property
    def web_source(self) -> Optional[str]:
        if self.kind != "webpage":
            return None
        return self.og_site_name or _humanize_domain(self.domain)

    @property
    def web_author(self) -> Optional[str]:
        if self.kind != "webpage":
            return None
        return self.author

    @property
    def web_summary(self) -> Optional[str]:
        if self.kind != "webpage":
            return None
        title = (self.og_title or self.page_title or "").strip()
        description = (self.og_description or "").strip()
        if not description:
            return None
        if title and description == title:
            return None
        return description

    @property
    def webpage_content_type(self) -> Optional[str]:
        if self.kind != "webpage":
            return None
        og_type = (self.og_type or "").lower()
        if og_type == "article":
            return "article"
        if og_type:
            return og_type
        return "page"


def inspect_url(url: str, timeout: float = 10.0) -> UrlInfo:
    normalized_url = _normalize_url(url)
    request = Request(normalized_url, headers=_request_headers())
    try:
        with urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            parsed = urlparse(final_url)
            content_type = response.headers.get_content_type()
            html = None
            if content_type == "text/html":
                html = response.read(300_000).decode("utf-8", errors="replace")
            info = UrlInfo(
                original_url=url,
                final_url=final_url,
                domain=parsed.netloc,
                content_type=content_type,
                status=getattr(response, "status", None),
            )
            if html:
                _populate_html_metadata(info, html)
                if info.og_image:
                    info.image_fetchable = _is_fetchable_image(info.og_image, timeout=timeout)
            if _needs_html_fallback(info):
                fallback_html = _fetch_html_with_curl(normalized_url)
                if fallback_html:
                    _populate_html_metadata(info, fallback_html)
                    if info.og_image and info.image_fetchable is None:
                        info.image_fetchable = _is_fetchable_image(info.og_image, timeout=timeout)
            return info
    except HTTPError as exc:
        parsed = urlparse(exc.geturl() or normalized_url)
        info = UrlInfo(
            original_url=url,
            final_url=exc.geturl() or normalized_url,
            domain=parsed.netloc,
            content_type=exc.headers.get_content_type() if exc.headers else None,
            status=exc.code,
            error=str(exc),
        )
        if _needs_html_fallback(info):
            fallback_html = _fetch_html_with_curl(normalized_url)
            if fallback_html:
                _populate_html_metadata(info, fallback_html)
                if info.og_image:
                    info.image_fetchable = _is_fetchable_image(info.og_image, timeout=timeout)
        return info
    except URLError as exc:
        parsed = urlparse(url)
        return UrlInfo(
            original_url=url,
            final_url=url,
            domain=parsed.netloc,
            content_type=None,
            status=None,
            error=str(exc.reason),
        )


def _populate_html_metadata(info: UrlInfo, html: str) -> None:
    parser = _MetadataParser()
    parser.feed(html)
    meta = parser.meta
    title_match = TITLE_RE.search(html)
    if title_match:
        info.page_title = _clean_html_text(title_match.group("title"))

    info.og_title = meta.get("og:title")
    info.og_description = meta.get("og:description")
    info.og_type = meta.get("og:type")
    info.og_image = meta.get("og:image")
    info.og_site_name = meta.get("og:site_name") or meta.get("application-name")
    info.author = meta.get("author")
    _populate_json_ld_metadata(info, html)


def _clean_html_text(value: str) -> str:
    return (
        value.replace("&amp;", "&")
        .replace("&#x27;", "'")
        .replace("&#039;", "'")
        .replace("&quot;", '"')
        .replace("&#x1f3b9;", "")
        .replace("&#x1fa95;", "")
        .strip()
    )


def _is_fetchable_image(url: str, timeout: float = 10.0) -> bool:
    request = Request(url, headers=_request_headers())
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.headers.get_content_type().startswith("image/")
    except (HTTPError, URLError):
        return False


def _needs_html_fallback(info: UrlInfo) -> bool:
    if info.kind not in {"spotify", "facebook", "webpage"}:
        return False
    return not any([info.og_title, info.og_description, info.og_image])


def _fetch_html_with_curl(url: str) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["curl", "-L", "--silent", url],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout[:300_000]


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if "spotify.com" not in domain:
        return url

    query = parse_qs(parsed.query)
    track_ids = query.get("track-id")
    if "/wrapped/share/" in parsed.path and track_ids:
        return f"https://open.spotify.com/track/{track_ids[0]}"

    return url


def _populate_json_ld_metadata(info: UrlInfo, html: str) -> None:
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(?P<body>.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
        for entry in _iter_json_ld_entries(payload):
            if not isinstance(entry, dict):
                continue
            if not info.author:
                author = _extract_author(entry.get("author"))
                if author:
                    info.author = author
            if not info.og_description:
                description = entry.get("description")
                if isinstance(description, str) and description.strip():
                    info.og_description = _clean_html_text(description)
            if not info.og_title:
                headline = entry.get("headline") or entry.get("name")
                if isinstance(headline, str) and headline.strip():
                    info.og_title = _clean_html_text(headline)
            if not info.og_site_name:
                publisher = entry.get("publisher")
                source = _extract_publisher_name(publisher)
                if source:
                    info.og_site_name = source
            if info.author and info.og_description and info.og_title and info.og_site_name:
                return


def _iter_json_ld_entries(payload):
    if isinstance(payload, list):
        for item in payload:
            yield from _iter_json_ld_entries(item)
        return
    if isinstance(payload, dict):
        if "@graph" in payload and isinstance(payload["@graph"], list):
            for item in payload["@graph"]:
                yield from _iter_json_ld_entries(item)
        yield payload


def _extract_author(value) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return _clean_html_text(value)
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return _clean_html_text(name)
    if isinstance(value, list):
        names = []
        for item in value:
            name = _extract_author(item)
            if name:
                names.append(name)
        if names:
            return ", ".join(dict.fromkeys(names))
    return None


def _extract_publisher_name(value) -> Optional[str]:
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return _clean_html_text(name)
    return None


def _humanize_domain(domain: str) -> Optional[str]:
    cleaned = domain.lower().strip()
    if cleaned.startswith("www."):
        cleaned = cleaned[4:]
    if not cleaned:
        return None
    root = cleaned.split(".")[0]
    if not root:
        return cleaned
    return root.replace("-", " ").title()


def download_og_image(info: UrlInfo, destination_dir: Path, timeout: float = 15.0) -> Optional[Path]:
    if not info.og_image:
        return None
    destination_dir.mkdir(parents=True, exist_ok=True)

    request = Request(info.og_image, headers=_request_headers())
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_type()
            if not content_type.startswith("image/"):
                return None
            suffix = mimetypes.guess_extension(content_type) or ".img"
            output_path = destination_dir / f"preview{suffix}"
            output_path.write_bytes(response.read())
            return output_path
    except (HTTPError, URLError, OSError):
        return None


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attrs_map = {name.lower(): (value or "") for name, value in attrs}
        key = attrs_map.get("property") or attrs_map.get("name")
        content = attrs_map.get("content")
        if key and content and key.lower() not in self.meta:
            self.meta[key.lower()] = _clean_html_text(content)
