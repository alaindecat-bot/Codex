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
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse, unquote, parse_qsl
from urllib.request import Request, urlopen

from .google_drive import DriveConfig, shared_file_metadata_from_url

TITLE_RE = re.compile(r"<title>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)
LOW_INFORMATION_DOMAINS = (
    "teams.microsoft.com",
    "teams.live.com",
    "zoom.us",
    "meet.google.com",
    "webex.com",
    "calendly.com",
    "cal.com",
    "whereby.com",
    "doodle.com",
    "meet.jit.si",
)
LOW_INFORMATION_TITLE_SUFFIX_RE = re.compile(
    r"\s*(?:[-|:]\s*)?(Teams|Zoom|Google Meet|Webex|Calendly|Cal\.com|Whereby|Doodle)\s*$",
    re.IGNORECASE,
)
GENERIC_LOW_INFORMATION_TITLES = {
    "join microsoft teams meeting",
    "microsoft teams meeting",
    "join zoom meeting",
    "zoom meeting",
    "google meet",
    "join the meeting now",
    "webex meeting",
}
LRCLIB_API_URL = "https://lrclib.net/api/search"
YOUTUBE_OEMBED_API_URL = "https://www.youtube.com/oembed"
LYRIC_TIMESTAMP_RE = re.compile(r"^\[[0-9:.]+\]\s*")
_LYRICS_CACHE: dict[tuple[str, str], Optional[str]] = {}
VIDEO_FROM_RE = re.compile(r"^Video from (?P<creator>.+)$", re.IGNORECASE)
SHARED_BY_RE = re.compile(r"^Shared by (?P<name>.+)$", re.IGNORECASE)
SUMMARY_MAX_LENGTH = 220
VIDEO_FILE_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
DOCUMENT_FILE_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".txt",
    ".csv",
    ".rtf",
    ".odt",
    ".ods",
    ".odp",
    ".numbers",
    ".pages",
    ".key",
}
GENERIC_SHARED_TITLES = {"dropbox", "google docs", "google drive", "google forms", "icloud"}


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
    spotify_lyrics: Optional[str] = None
    error: Optional[str] = None

    @property
    def kind(self) -> str:
        domain = self.domain.lower()
        content_type = (self.content_type or "").lower()
        if "spotify.com" in domain:
            return "spotify"
        if _is_youtube_domain(domain):
            return "youtube"
        if _is_dubb_domain(domain):
            return "dubb"
        if _is_google_workspace_domain(domain):
            return "google_drive"
        if _is_dropbox_domain(domain):
            return "dropbox"
        if _is_icloud_domain(domain):
            return "icloud"
        if _is_linkedin_domain(domain):
            return "linkedin"
        if _is_x_domain(domain):
            return "x"
        if _is_swr_domain(domain):
            return "swr"
        if "facebook.com" in domain or "fb.watch" in domain:
            return "facebook"
        if _is_low_information_link(
            domain,
            self.final_url or self.original_url,
            self.og_title,
            self.page_title,
            self.og_site_name,
        ):
            return "meeting"
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
    def source_label(self) -> str:
        if self.kind == "youtube":
            return "YouTube"
        if self.kind == "dubb":
            return "Dubb"
        if self.kind == "dropbox":
            return "Dropbox"
        if self.kind == "google_drive":
            resource_type = self.shared_resource_type
            if resource_type == "document":
                return "Google Docs"
            if resource_type == "form":
                return "Google Forms"
            if resource_type == "sheet":
                return "Google Sheets"
            if resource_type == "slides":
                return "Google Slides"
            return "Google Drive"
        if self.kind == "icloud":
            resource_type = self.shared_resource_type
            if resource_type == "numbers":
                return "iCloud Numbers"
            if resource_type == "pages":
                return "iCloud Pages"
            if resource_type == "keynote":
                return "iCloud Keynote"
            return "iCloud"
        if self.kind == "linkedin":
            return "LinkedIn"
        if self.kind == "x":
            return "X"
        if self.kind == "swr":
            return "SWR"
        if self.og_site_name:
            return self.og_site_name
        if self.kind == "meeting":
            domain = self.domain.lower()
            if "teams" in domain:
                return "Teams"
            if "zoom" in domain:
                return "Zoom"
            if "meet.google" in domain:
                return "Google Meet"
            if "webex" in domain:
                return "Webex"
            if "calendly" in domain:
                return "Calendly"
            if domain == "cal.com" or domain.endswith(".cal.com"):
                return "Cal.com"
            if "whereby" in domain:
                return "Whereby"
            if "doodle" in domain:
                return "Doodle"
            if "jit.si" in domain:
                return "Jitsi"
        return _humanize_domain(self.domain)

    @property
    def low_information_title(self) -> Optional[str]:
        if self.kind != "meeting":
            return None
        for candidate in (self.og_title, self.page_title):
            cleaned = _clean_low_information_title(candidate)
            if cleaned:
                return cleaned
        return None

    @property
    def lyrics_searchable(self) -> Optional[bool]:
        if self.kind != "spotify":
            return None
        return bool(self.spotify_lyrics)

    @property
    def youtube_title(self) -> Optional[str]:
        if self.kind != "youtube":
            return None
        title = (self.og_title or self.page_title or "").strip()
        return title or None

    @property
    def youtube_creator(self) -> Optional[str]:
        if self.kind != "youtube":
            return None
        return self.author

    @property
    def youtube_resource_type(self) -> Optional[str]:
        if self.kind != "youtube":
            return None
        path = urlparse(self.final_url or self.original_url).path.strip("/").lower()
        if path.startswith("shorts/"):
            return "short"
        if path == "watch" or path == "embed":
            return "video"
        if path.startswith("@") or path.startswith("channel/") or path.startswith("user/") or path.startswith("c/"):
            return "channel"
        if path == "playlist":
            return "playlist"
        if "/playlist" in path:
            return "playlist"
        return "video"

    @property
    def youtube_label(self) -> Optional[str]:
        if self.kind != "youtube":
            return None
        resource_type = self.youtube_resource_type
        if resource_type == "short":
            return "Short YouTube"
        if resource_type == "channel":
            return "Chaine YouTube"
        if resource_type == "playlist":
            return "Playlist YouTube"
        return "Video YouTube"

    @property
    def spotify_title(self) -> Optional[str]:
        if self.kind != "spotify":
            return None
        title = self.og_title or self.page_title
        if not title:
            return None
        if title.endswith(" | Spotify"):
            title = title.removesuffix(" | Spotify")
        return title.strip() or None

    @property
    def dubb_title(self) -> Optional[str]:
        if self.kind != "dubb":
            return None
        title = (self.og_title or self.page_title or "").strip()
        return title or None

    @property
    def dubb_creator(self) -> Optional[str]:
        if self.kind != "dubb":
            return None
        if self.author:
            return self.author
        description = (self.og_description or "").strip()
        match = VIDEO_FROM_RE.match(description)
        if match:
            return match.group("creator").strip() or None
        return None

    @property
    def shared_title(self) -> Optional[str]:
        if self.kind == "dropbox":
            title = _clean_generic_shared_title(self.og_title or self.page_title)
            if title:
                return title
            return _title_from_url_filename(self.final_url or self.original_url)
        if self.kind == "google_drive":
            title = _clean_generic_shared_title(self.og_title or self.page_title)
            if title:
                for suffix in (
                    " - Google Docs",
                    " - Google Forms",
                    " - Google Sheets",
                    " - Google Slides",
                    " - Google Drive",
                ):
                    if title.endswith(suffix):
                        title = title.removesuffix(suffix).strip()
                return title or None
            return None
        if self.kind == "icloud":
            title = _clean_generic_shared_title(self.og_title or self.page_title)
            return title or _title_from_url_fragment(self.final_url or self.original_url)
        return None

    @property
    def shared_resource_type(self) -> Optional[str]:
        url = self.final_url or self.original_url
        parsed = urlparse(url)
        path = parsed.path.strip("/").lower()
        host = self.domain.lower()
        suffix = _path_suffix_from_url(url)
        og_type = (self.og_type or "").lower()
        if self.kind == "dropbox":
            if "video" in og_type:
                return "video"
            if suffix in VIDEO_FILE_SUFFIXES:
                return "video"
            if suffix in DOCUMENT_FILE_SUFFIXES:
                return "document"
            return "file"
        if self.kind == "google_drive":
            if "video" in og_type:
                return "video"
            if host == "docs.google.com":
                if path.startswith("document/"):
                    return "document"
                if path.startswith("forms/"):
                    return "form"
                if path.startswith("spreadsheets/"):
                    return "sheet"
                if path.startswith("presentation/"):
                    return "slides"
            if suffix in VIDEO_FILE_SUFFIXES:
                return "video"
            if path.startswith("file/") or "/file/" in path:
                return "file"
            if "folders/" in path:
                return "folder"
            return "file"
        if self.kind == "icloud":
            if "video" in og_type:
                return "video"
            if path.startswith("numbers/"):
                return "numbers"
            if path.startswith("pages/"):
                return "pages"
            if path.startswith("keynote/"):
                return "keynote"
            if suffix in VIDEO_FILE_SUFFIXES:
                return "video"
            return "file"
        return None

    @property
    def shared_type_label(self) -> Optional[str]:
        resource_type = self.shared_resource_type
        if self.kind == "dropbox":
            if resource_type == "video":
                return "Video partagee (Dropbox)"
            if resource_type == "document":
                return "Document partage (Dropbox)"
            return "Fichier partage (Dropbox)"
        if self.kind == "google_drive":
            if resource_type == "document":
                return "Document partage (Google Docs)"
            if resource_type == "form":
                return "Formulaire partage (Google Forms)"
            if resource_type == "sheet":
                return "Tableur partage (Google Sheets)"
            if resource_type == "slides":
                return "Presentation partagee (Google Slides)"
            if resource_type == "folder":
                return "Dossier partage (Google Drive)"
            if resource_type == "video":
                return "Video partagee (Google Drive)"
            return "Fichier partage (Google Drive)"
        if self.kind == "icloud":
            if resource_type == "numbers":
                return "Document partage (iCloud Numbers)"
            if resource_type == "pages":
                return "Document partage (iCloud Pages)"
            if resource_type == "keynote":
                return "Presentation partagee (iCloud Keynote)"
            if resource_type == "video":
                return "Video partagee (iCloud)"
            return "Fichier partage (iCloud)"
        return None

    @property
    def shared_by(self) -> Optional[str]:
        if self.kind not in {"google_drive", "icloud"}:
            return None
        description = (self.og_description or "").strip()
        match = SHARED_BY_RE.match(description)
        if match:
            return match.group("name").strip() or None
        return None

    @property
    def shared_video_source_url(self) -> Optional[str]:
        if self.shared_resource_type != "video":
            return None
        url = self.final_url or self.original_url
        if self.kind == "dropbox":
            parsed = urlparse(url)
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            query.pop("dl", None)
            query["raw"] = "1"
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", urlencode(query), ""))
        return None

    @property
    def spotify_resource_type(self) -> Optional[str]:
        if self.kind != "spotify":
            return None
        path = urlparse(self.final_url or self.original_url).path.lower()
        if "/track/" in path:
            return "track"
        if "/album/" in path:
            return "album"
        if "/playlist/" in path:
            return "playlist"
        if "/artist/" in path:
            return "artist"
        if "/episode/" in path:
            return "episode"
        return None

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
        path = urlparse(self.final_url or self.original_url).path.lower()
        if "/posts/" in path:
            return "post"
        if "/videos/" in path or "fb.watch" in self.domain.lower():
            return "video"
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
        return _truncate_summary(description)

    @property
    def linkedin_title(self) -> Optional[str]:
        if self.kind != "linkedin":
            return None
        title = (self.og_title or self.page_title or "").strip()
        if not title:
            return None
        if title.endswith(" | LinkedIn"):
            title = title.removesuffix(" | LinkedIn").strip()
        return _truncate_summary(title, max_length=160)

    @property
    def linkedin_content_label(self) -> Optional[str]:
        if self.kind != "linkedin":
            return None
        path = urlparse(self.final_url or self.original_url).path.lower()
        if path.startswith("/in/") or path.startswith("/pub/"):
            return "Profil LinkedIn"
        if "/posts/" in path:
            return "Post LinkedIn"
        og_type = (self.og_type or "").lower()
        if og_type == "profile":
            return "Profil LinkedIn"
        if og_type == "article":
            return "Post LinkedIn"
        return "Lien LinkedIn"

    @property
    def linkedin_source(self) -> Optional[str]:
        if self.kind != "linkedin":
            return None
        if self.author:
            return self.author
        title = (self.og_title or self.page_title or "").strip()
        if " | " in title:
            parts = [part.strip() for part in title.split(" | ") if part.strip()]
            if parts:
                return parts[-1]
        if " - " in title:
            return title.split(" - ", 1)[0].strip() or None
        return None

    @property
    def linkedin_summary(self) -> Optional[str]:
        if self.kind != "linkedin":
            return None
        description = (self.og_description or "").strip()
        title = (self.og_title or self.page_title or "").strip()
        if not description or description == title:
            return None
        return _truncate_summary(description)

    @property
    def x_content_label(self) -> Optional[str]:
        if self.kind != "x":
            return None
        path = urlparse(self.final_url or self.original_url).path.lower()
        if "/status/" in path:
            return "Post X"
        return "Lien X"

    @property
    def x_source(self) -> Optional[str]:
        if self.kind != "x":
            return None
        if self.author:
            return self.author
        path = urlparse(self.final_url or self.original_url).path.strip("/")
        if not path:
            return None
        handle = path.split("/", 1)[0].strip()
        if not handle:
            return None
        return f"@{handle}"

    @property
    def x_title(self) -> Optional[str]:
        if self.kind != "x":
            return None
        title = (self.og_title or self.page_title or "").strip()
        if title:
            return _truncate_summary(title, max_length=160)
        source = self.x_source
        if source and self.x_content_label == "Post X":
            return f"Post X de {source}"
        return self.x_content_label

    @property
    def x_summary(self) -> Optional[str]:
        if self.kind != "x":
            return None
        description = (self.og_description or "").strip()
        if not description:
            return None
        return _truncate_summary(description)

    @property
    def swr_title(self) -> Optional[str]:
        if self.kind != "swr":
            return None
        title = (self.og_title or self.page_title or "").strip()
        return _truncate_summary(title, max_length=180) if title else None

    @property
    def swr_content_label(self) -> Optional[str]:
        if self.kind != "swr":
            return None
        og_type = (self.og_type or "").lower()
        if "video" in og_type:
            return "Video SWR"
        if "audio" in og_type:
            return "Audio SWR"
        if "article" in og_type:
            return "Article SWR"
        return "Page SWR"

    @property
    def swr_summary(self) -> Optional[str]:
        if self.kind != "swr":
            return None
        description = (self.og_description or "").strip()
        title = (self.og_title or self.page_title or "").strip()
        if not description or description == title:
            return None
        return _truncate_summary(description)

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
        return _truncate_summary(description)

    @property
    def webpage_content_type(self) -> Optional[str]:
        if self.kind != "webpage":
            return None
        og_type = (self.og_type or "").lower()
        if "video" in og_type:
            return "Video"
        if "audio" in og_type:
            return "Audio"
        if og_type == "article":
            return "Article"
        if og_type:
            return _humanize_machine_label(og_type)
        return "Page web"


def inspect_url(url: str, timeout: float = 10.0) -> UrlInfo:
    return inspect_url_with_google(url, timeout=timeout, drive_config=None)


def inspect_url_with_google(url: str, timeout: float = 10.0, drive_config: DriveConfig | None = None) -> UrlInfo:
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
            _populate_google_drive_metadata(info, drive_config=drive_config, timeout=timeout)
            _populate_youtube_metadata(info, timeout=timeout)
            _populate_spotify_metadata(info, timeout=timeout)
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
        _populate_google_drive_metadata(info, drive_config=drive_config, timeout=timeout)
        _populate_youtube_metadata(info, timeout=timeout)
        _populate_spotify_metadata(info, timeout=timeout)
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

    info.og_title = meta.get("og:title") or meta.get("twitter:title")
    info.og_description = meta.get("og:description") or meta.get("twitter:description")
    info.og_type = meta.get("og:type")
    info.og_image = (
        meta.get("og:image")
        or meta.get("og:image:url")
        or meta.get("og:image:secure_url")
        or meta.get("twitter:image")
    )
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


def _is_youtube_domain(domain: str) -> bool:
    host = domain.lower().split(":", 1)[0]
    return (
        host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "youtu.be"
    )


def _is_dubb_domain(domain: str) -> bool:
    host = domain.lower().split(":", 1)[0]
    return host == "dubb.com" or host.endswith(".dubb.com")


def _is_google_workspace_domain(domain: str) -> bool:
    host = domain.lower().split(":", 1)[0]
    return host == "docs.google.com" or host == "drive.google.com"


def _is_dropbox_domain(domain: str) -> bool:
    host = domain.lower().split(":", 1)[0]
    return host == "dropbox.com" or host.endswith(".dropbox.com")


def _is_icloud_domain(domain: str) -> bool:
    host = domain.lower().split(":", 1)[0]
    return host == "icloud.com" or host.endswith(".icloud.com")


def _is_linkedin_domain(domain: str) -> bool:
    host = domain.lower().split(":", 1)[0]
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def _is_x_domain(domain: str) -> bool:
    host = domain.lower().split(":", 1)[0]
    return host in {"x.com", "twitter.com"} or host.endswith(".x.com") or host.endswith(".twitter.com")


def _is_swr_domain(domain: str) -> bool:
    host = domain.lower().split(":", 1)[0]
    return host == "swr.de" or host.endswith(".swr.de")


def _path_suffix_from_url(url: str) -> str:
    path = urlparse(url).path
    filename = Path(unquote(path)).name
    return Path(filename).suffix.lower()


def _title_from_url_filename(url: str) -> Optional[str]:
    path = urlparse(url).path
    filename = Path(unquote(path)).name
    if not filename:
        return None
    stem = Path(filename).stem
    if not stem:
        return None
    cleaned = stem.replace("_", " ").replace("-", " ").strip()
    return cleaned or stem


def _title_from_url_fragment(url: str) -> Optional[str]:
    fragment = urlparse(url).fragment.strip()
    if not fragment:
        return None
    cleaned = unquote(fragment).replace("_", " ").strip()
    return cleaned or None


def _clean_generic_shared_title(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.casefold() in GENERIC_SHARED_TITLES:
        return None
    return cleaned


def _truncate_summary(value: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= max_length:
        return compact
    truncated = compact[: max_length - 1].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0].rstrip()
    return f"{truncated}…"


def _humanize_machine_label(value: str) -> str:
    base = value.split(".", 1)[0]
    base = base.replace("_", " ").replace("-", " ").strip()
    if not base:
        return "Page web"
    return base[:1].upper() + base[1:]


def _is_low_information_link(
    domain: str,
    url: str,
    og_title: Optional[str],
    page_title: Optional[str],
    og_site_name: Optional[str],
) -> bool:
    host = domain.lower().split(":", 1)[0]
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in LOW_INFORMATION_DOMAINS):
        return True

    path = urlparse(url).path.lower()
    if any(token in host for token in ("teams", "zoom", "webex", "whereby")) and any(
        marker in path for marker in ("/join", "/meet", "/meeting", "/l/meeting", "/room")
    ):
        return True

    title_bits = " ".join(part for part in (og_title, page_title, og_site_name) if part)
    normalized_title = _normalize_match_text(title_bits)
    if normalized_title in GENERIC_LOW_INFORMATION_TITLES:
        return True
    return False


def _clean_low_information_title(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = LOW_INFORMATION_TITLE_SUFFIX_RE.sub("", value).strip(" -|:")
    normalized = _normalize_match_text(cleaned)
    if not normalized or normalized in GENERIC_LOW_INFORMATION_TITLES:
        return None
    generic_tokens = {
        "join",
        "meeting",
        "meet",
        "room",
        "video",
        "call",
        "conference",
        "microsoft",
        "teams",
        "zoom",
        "google",
        "webex",
        "calendly",
        "cal",
        "whereby",
        "doodle",
        "jitsi",
        "schedule",
        "booking",
        "book",
        "appointment",
        "invite",
        "online",
        "now",
    }
    words = normalized.split()
    if words and all(word in generic_tokens for word in words):
        return None
    return cleaned or None


def _is_fetchable_image(url: str, timeout: float = 10.0) -> bool:
    request = Request(url, headers=_request_headers())
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.headers.get_content_type().startswith("image/")
    except (HTTPError, URLError):
        return False


def _needs_html_fallback(info: UrlInfo) -> bool:
    if info.kind not in {
        "spotify",
        "facebook",
        "webpage",
        "youtube",
        "dubb",
        "dropbox",
        "google_drive",
        "icloud",
        "linkedin",
        "x",
        "swr",
    }:
        return False
    return not any([info.og_title, info.og_description, info.og_image])


def _fetch_html_with_curl(url: str) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["curl", "-L", "--silent", url],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return _decode_html_payload(completed.stdout[:300_000])


def _decode_html_payload(payload: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


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
    url = _strip_trailing_url_punctuation(url)
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if "spotify.com" not in domain:
        return url

    query = parse_qs(parsed.query)
    track_ids = query.get("track-id")
    if "/wrapped/share/" in parsed.path and track_ids:
        return f"https://open.spotify.com/track/{track_ids[0]}"

    return url


def _populate_youtube_metadata(info: UrlInfo, timeout: float = 10.0) -> None:
    if info.kind != "youtube":
        return
    info.og_site_name = info.og_site_name or "YouTube"
    oembed = _fetch_youtube_oembed(info.final_url or info.original_url, timeout=timeout)
    if oembed:
        if not info.og_title:
            info.og_title = oembed.get("title")
        if not info.author:
            info.author = oembed.get("author_name")
        if not info.og_image:
            info.og_image = oembed.get("thumbnail_url")
        if not info.og_type:
            oembed_type = oembed.get("type")
            if oembed_type == "video":
                info.og_type = info.youtube_resource_type or "video"
            elif isinstance(oembed_type, str) and oembed_type.strip():
                info.og_type = oembed_type.strip().lower()
    if info.og_image and info.image_fetchable is None:
        info.image_fetchable = _is_fetchable_image(info.og_image, timeout=timeout)


def _populate_google_drive_metadata(
    info: UrlInfo,
    drive_config: DriveConfig | None = None,
    timeout: float = 10.0,
) -> None:
    if info.kind != "google_drive" or drive_config is None:
        return
    metadata = shared_file_metadata_from_url(info.final_url or info.original_url, drive_config)
    if not metadata:
        return
    name = metadata.get("name")
    if isinstance(name, str) and name.strip():
        info.og_title = name.strip()
    mime_type = metadata.get("mimeType")
    if isinstance(mime_type, str) and mime_type.strip():
        info.og_type = _google_mime_type_to_og_type(mime_type)
    thumbnail = metadata.get("thumbnailLink")
    if isinstance(thumbnail, str) and thumbnail.strip():
        info.og_image = thumbnail.strip()
    owners = metadata.get("owners")
    if isinstance(owners, list) and owners:
        owner = owners[0]
        if isinstance(owner, dict):
            display_name = owner.get("displayName")
            if isinstance(display_name, str) and display_name.strip():
                info.author = display_name.strip()
                if not info.og_description:
                    info.og_description = f"Shared by {info.author}"
    if info.og_image and info.image_fetchable is None:
        info.image_fetchable = _is_fetchable_image(info.og_image, timeout=timeout)
    if info.og_title or info.og_image:
        info.error = None


def _google_mime_type_to_og_type(mime_type: str) -> str:
    mapping = {
        "application/vnd.google-apps.document": "document",
        "application/vnd.google-apps.spreadsheet": "sheet",
        "application/vnd.google-apps.presentation": "slides",
        "application/vnd.google-apps.form": "form",
        "application/vnd.google-apps.folder": "folder",
    }
    if mime_type in mapping:
        return mapping[mime_type]
    if mime_type.startswith("video/"):
        return "video.other"
    if mime_type.startswith("image/"):
        return "image"
    if mime_type.startswith("audio/"):
        return "audio"
    return mime_type


def _fetch_youtube_oembed(url: str, timeout: float = 10.0) -> Optional[dict[str, str]]:
    canonical_url = _youtube_oembed_target_url(url)
    if canonical_url is None:
        return None
    query = urlencode({"url": canonical_url, "format": "json"})
    request = Request(
        f"{YOUTUBE_OEMBED_API_URL}?{query}",
        headers={
            **_request_headers(),
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _youtube_oembed_target_url(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    query = parse_qs(parsed.query)
    if host == "youtu.be":
        video_id = path.split("/", 1)[0]
        if not video_id:
            return None
        return f"https://www.youtube.com/watch?v={video_id}"
    if host.endswith("youtube.com"):
        if path == "watch":
            video_id = query.get("v", [None])[0]
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"
        if path.startswith("shorts/"):
            short_id = path.split("/", 1)[1].split("/", 1)[0]
            if short_id:
                return f"https://www.youtube.com/shorts/{short_id}"
        if path == "playlist":
            playlist_id = query.get("list", [None])[0]
            if playlist_id:
                return f"https://www.youtube.com/playlist?list={playlist_id}"
        if path.startswith("@") or path.startswith("channel/") or path.startswith("user/") or path.startswith("c/"):
            return urlunparse((parsed.scheme or "https", "www.youtube.com", f"/{path}", "", "", ""))
    return None


def _strip_trailing_url_punctuation(url: str) -> str:
    cleaned = url.rstrip(".,;:!?")
    for opener, closer in (("(", ")"), ("[", "]"), ("{", "}")):
        while cleaned.endswith(closer) and cleaned.count(closer) > cleaned.count(opener):
            cleaned = cleaned[:-1]
    return cleaned


def _populate_spotify_metadata(info: UrlInfo, timeout: float = 10.0) -> None:
    if info.kind != "spotify":
        return
    if info.spotify_resource_type != "track":
        return
    title = info.spotify_title
    artists = info.spotify_artists
    if not title or not artists:
        return
    info.spotify_lyrics = _resolve_spotify_lyrics(title, artists, timeout=timeout)


def _resolve_spotify_lyrics(track_name: str, artist_name: str, timeout: float = 10.0) -> Optional[str]:
    artist_variants = [artist_name]
    primary_artist = artist_name.split(",")[0].strip()
    if primary_artist and primary_artist not in artist_variants:
        artist_variants.append(primary_artist)

    title_variants = [track_name]
    stripped_brackets = re.sub(r"\s*[\[(].*?[\])]\s*", " ", track_name).strip()
    if stripped_brackets and stripped_brackets not in title_variants:
        title_variants.append(stripped_brackets)
    leading_title = re.split(r"\s*[\[(]", track_name, maxsplit=1)[0].strip()
    if leading_title and leading_title not in title_variants:
        title_variants.append(leading_title)

    for title_variant in title_variants:
        for artist_variant in artist_variants:
            lyrics = _fetch_spotify_lyrics(title_variant, artist_variant, timeout=timeout)
            if lyrics:
                return lyrics
    return None


def _fetch_spotify_lyrics(track_name: str, artist_name: str, timeout: float = 10.0) -> Optional[str]:
    cache_key = (track_name.casefold(), artist_name.casefold())
    if cache_key in _LYRICS_CACHE:
        return _LYRICS_CACHE[cache_key]

    query = urlencode({"track_name": track_name, "artist_name": artist_name})
    request = Request(
        f"{LRCLIB_API_URL}?{query}",
        headers={
            **_request_headers(),
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (HTTPError, URLError, json.JSONDecodeError):
        _LYRICS_CACHE[cache_key] = None
        return None

    lyrics = _select_best_lyrics_match(payload, track_name, artist_name)
    _LYRICS_CACHE[cache_key] = lyrics
    return lyrics


def _select_best_lyrics_match(payload, track_name: str, artist_name: str) -> Optional[str]:
    if not isinstance(payload, list):
        return None

    best_score = -1
    best_lyrics: Optional[str] = None
    target_track = _normalize_match_text(track_name)
    target_artist = _normalize_match_text(artist_name.split(",")[0])

    for entry in payload:
        if not isinstance(entry, dict):
            continue
        plain = entry.get("plainLyrics") or entry.get("plain_lyrics")
        synced = entry.get("syncedLyrics") or entry.get("synced_lyrics")
        lyrics = plain or _strip_lyric_timestamps(synced)
        lyrics = _clean_lyrics_text(lyrics)
        if not lyrics:
            continue
        score = 0
        entry_track = _normalize_match_text(str(entry.get("trackName") or entry.get("track_name") or ""))
        entry_artist = _normalize_match_text(str(entry.get("artistName") or entry.get("artist_name") or ""))
        if entry_track == target_track:
            score += 2
        elif target_track and target_track in entry_track:
            score += 1
        if entry_artist == target_artist:
            score += 2
        elif target_artist and target_artist in entry_artist:
            score += 1
        if plain:
            score += 1
        if score > best_score:
            best_score = score
            best_lyrics = lyrics

    return best_lyrics


def _normalize_match_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _strip_lyric_timestamps(value: object) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    lines = [LYRIC_TIMESTAMP_RE.sub("", line).rstrip() for line in value.splitlines()]
    return "\n".join(lines)


def _clean_lyrics_text(value: object) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    lines = [line.strip() for line in value.splitlines()]
    cleaned_lines: list[str] = []
    previous_blank = True
    for line in lines:
        if not line:
            if not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue
        cleaned_lines.append(line)
        previous_blank = False
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()
    return "\n".join(cleaned_lines) or None


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
