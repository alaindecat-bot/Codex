from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import mimetypes
from pathlib import Path

from .docx_writer import write_docx
from .engine import EngineRequest, EngineResult, EngineWarning
from .google_drive import DriveConfig, ensure_drive_service, ensure_folder, folder_web_link, upload_file
from .interactive import build_summary_lines_with_initials
from .parser import Message, parse_chat
from .reply_analysis import semantic_scoring_candidates
from .url_tools import UrlInfo, inspect_url
from .zip_reader import extract_zip


@dataclass(frozen=True)
class PreparedConversation:
    messages: list[Message]
    authors: list[str]


def prepare_conversation(input_zip: Path) -> PreparedConversation:
    extracted = extract_zip(input_zip)
    try:
        chat_text = read_chat_text(extracted.chat_file)
        messages = parse_chat(chat_text, extracted.root_dir)
        authors = list(dict.fromkeys(message.author for message in messages))
        return PreparedConversation(messages=messages, authors=authors)
    finally:
        extracted.temp_dir.cleanup()


def generate_document(request: EngineRequest, drive_config: DriveConfig | None = None) -> EngineResult:
    extracted = extract_zip(request.input_zip)
    warnings: list[EngineWarning] = []
    logs: list[str] = []

    try:
        chat_text, chat_encoding = read_chat_text_with_encoding(extracted.chat_file)
        messages = parse_chat(chat_text, extracted.root_dir)
        logs.append(f"Read chat text using {chat_encoding}.")

        summary_lines = (
            build_summary_lines_with_initials(messages, datetime.now(), request.initials_by_author)
            if request.profile.include_summary
            else None
        )

        url_infos: dict[str, UrlInfo] = {}
        if request.profile.enrich_public_urls and request.profile.network.allow_public_url_enrichment:
            url_infos = inspect_message_urls(messages)
            logs.append(f"Resolved {len(url_infos)} unique URLs.")

        attachment_links: dict[Path, str] = {}
        video_folder_link: str | None = None
        if request.profile.supports_drive_uploads():
            if drive_config is None:
                warnings.append(
                    EngineWarning(
                        code="drive_config_missing",
                        message="Video mode requires Google Drive, but no Drive configuration was provided.",
                    )
                )
            else:
                try:
                    attachment_links, folder_id = upload_video_attachments(messages, drive_config)
                    video_folder_link = folder_web_link(drive_config, folder_id=folder_id)
                    logs.append(f"Uploaded {len(attachment_links)} video attachment(s) to Google Drive.")
                except Exception as exc:
                    warnings.append(
                        EngineWarning(
                            code="drive_upload_failed",
                            message=f"Google Drive upload failed; continuing without video links. {exc}",
                        )
                    )

        reply_links = {candidate.response_index: candidate for candidate in semantic_scoring_candidates(messages)}
        logs.append(f"Detected {len(reply_links)} reply link(s).")

        write_docx(
            request.output_docx,
            messages,
            request.initials_by_author,
            url_infos=url_infos if request.profile.enrich_public_urls else None,
            summary_lines=summary_lines,
            attachment_links=attachment_links,
            reply_links=reply_links,
            video_mode=request.profile.video_mode,
            video_folder_link=video_folder_link,
        )
    finally:
        extracted.temp_dir.cleanup()

    return EngineResult(
        output_docx=request.output_docx,
        warnings=warnings,
        logs=logs,
    )


def build_initials_map(authors: list[str], self_name: str, other_initial: str) -> dict[str, str]:
    counts = Counter(authors)
    initials: dict[str, str] = {}
    normalized_self = self_name.strip().casefold()

    for author, _count in counts.most_common():
        if author.strip().casefold() == normalized_self:
            initials[author] = "A"
        elif author not in initials:
            initials[author] = other_initial.upper()

    return initials


def inspect_message_urls(messages: list[Message]) -> dict[str, UrlInfo]:
    urls: list[str] = []
    for message in messages:
        urls.extend(message.urls)
    unique_urls = list(dict.fromkeys(urls))
    return {url: inspect_url(url) for url in unique_urls}


def upload_video_attachments(messages: list[Message], drive_config: DriveConfig) -> tuple[dict[Path, str], str]:
    links: dict[Path, str] = {}
    service = ensure_drive_service(drive_config)
    folder_id = ensure_folder(service, drive_config.folder_name)
    for message in messages:
        attachment = getattr(message, "attachment", None)
        if attachment is None:
            continue
        if attachment.path in links:
            continue
        if attachment.path.suffix.lower() not in {".mp4", ".mov", ".m4v"}:
            continue
        mime_type, _ = mimetypes.guess_type(str(attachment.path))
        links[attachment.path] = upload_file(
            attachment.path,
            drive_config,
            mime_type=mime_type,
            folder_id=folder_id,
            service=service,
        )
    return links, folder_id


def read_chat_text(chat_file: Path) -> str:
    text, _encoding = read_chat_text_with_encoding(chat_file)
    return text


def read_chat_text_with_encoding(chat_file: Path) -> tuple[str, str]:
    payload = chat_file.read_bytes()
    encodings = [
        "utf-8",
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "cp1252",
        "latin-1",
    ]

    for encoding in encodings:
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    return payload.decode("utf-8", errors="replace"), "utf-8-replace"
