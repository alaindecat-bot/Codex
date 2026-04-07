from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import mimetypes
from pathlib import Path
from time import perf_counter

from .audio_transcription import AudioTranscript, transcribe_audio_attachments
from .docx_writer import write_docx
from .engine import EngineRequest, EngineResult, EngineWarning
from .google_drive import DriveConfig, ensure_drive_service, ensure_folder, folder_web_link, upload_file
from .interactive import build_summary_lines_with_initials
from .parser import Message, parse_chat
from .perf import PerformanceRecorder
from .performance_visualization import write_performance_svg
from .reply_analysis import semantic_scoring_candidates
from .url_tools import UrlInfo, inspect_url_with_google
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
    profiler = PerformanceRecorder()
    started = perf_counter()
    with profiler.time("stage", "extract_zip"):
        extracted = extract_zip(request.input_zip)
    warnings: list[EngineWarning] = []
    logs: list[str] = []

    try:
        with profiler.time("stage", "read_chat_text"):
            chat_text, chat_encoding = read_chat_text_with_encoding(extracted.chat_file)
        with profiler.time("stage", "parse_chat"):
            messages = parse_chat(chat_text, extracted.root_dir)
        profiler.set_counter("message_count", len(messages))
        logs.append(f"Read chat text using {chat_encoding}.")

        summary_lines = None
        if request.profile.include_summary:
            with profiler.time("stage", "build_summary"):
                summary_lines = build_summary_lines_with_initials(
                    messages,
                    datetime.now(),
                    request.initials_by_author,
                )

        url_infos: dict[str, UrlInfo] = {}
        if request.profile.enrich_public_urls and request.profile.network.allow_public_url_enrichment:
            with profiler.time("stage", "url_enrichment"):
                url_infos = inspect_message_urls(messages, drive_config=drive_config, profiler=profiler)
            profiler.set_counter("unique_url_count", len(url_infos))
            logs.append(f"Resolved {len(url_infos)} unique URLs.")

        attachment_links: dict[Path, str] = {}
        video_folder_link: str | None = None
        audio_transcripts: dict[Path, AudioTranscript] = {}
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
                    with profiler.time("stage", "upload_video_attachments"):
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

        if request.profile.audio_transcription_enabled:
            try:
                with profiler.time("stage", "audio_transcription"):
                    audio_transcripts = transcribe_audio_attachments(messages)
                success_count = sum(1 for transcript in audio_transcripts.values() if transcript.available)
                failure_count = sum(1 for transcript in audio_transcripts.values() if not transcript.available)
                if audio_transcripts:
                    logs.append(f"Transcribed {success_count} audio attachment(s).")
                if failure_count:
                    warnings.append(
                        EngineWarning(
                            code="audio_transcription_partial",
                            message=f"{failure_count} audio attachment(s) could not be transcribed.",
                        )
                    )
            except Exception as exc:
                warnings.append(
                    EngineWarning(
                        code="audio_transcription_failed",
                        message=f"Audio transcription failed; continuing without transcripts. {exc}",
                        )
                    )

        with profiler.time("stage", "reply_analysis"):
            reply_links = {candidate.response_index: candidate for candidate in semantic_scoring_candidates(messages)}
        logs.append(f"Detected {len(reply_links)} reply link(s).")

        with profiler.time("stage", "write_docx"):
            write_docx(
                request.output_docx,
                messages,
                request.initials_by_author,
                url_infos=url_infos if request.profile.enrich_public_urls else None,
                summary_lines=summary_lines,
                attachment_links=attachment_links,
                audio_transcripts=audio_transcripts,
                reply_links=reply_links,
                spotify_mode=request.profile.spotify_mode,
                spotify_poem_columns=2 if request.profile.spotify_mode == "poeme" else 1,
                spotify_poem_font_size_pt=9.0 if request.profile.spotify_mode == "poeme" else None,
                video_mode=request.profile.video_mode,
                video_folder_link=video_folder_link,
                profiler=profiler,
            )
    finally:
        profiler.record("stage", "generate_document", perf_counter() - started)
        extracted.temp_dir.cleanup()

    performance_report_path: Path | None = None
    performance_summary_path: Path | None = None
    performance_svg_path: Path | None = None
    if request.write_performance_report:
        logs.extend(profiler.summary_lines())
        performance_report_path = request.output_docx.with_name(f"{request.output_docx.stem}-performance.json")
        performance_summary_path = request.output_docx.with_name(f"{request.output_docx.stem}-performance.txt")
        profiler.write_json(performance_report_path)
        profiler.write_text(performance_summary_path)
        performance_svg_path = write_performance_svg(performance_report_path)

    return EngineResult(
        output_docx=request.output_docx,
        warnings=warnings,
        logs=logs,
        performance_report_path=performance_report_path,
        performance_summary_path=performance_summary_path,
        performance_svg_path=performance_svg_path,
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


def inspect_message_urls(
    messages: list[Message],
    drive_config: DriveConfig | None = None,
    profiler: PerformanceRecorder | None = None,
) -> dict[str, UrlInfo]:
    urls: list[str] = []
    for message in messages:
        urls.extend(message.urls)
    if profiler is not None:
        profiler.set_counter("url_mentions", len(urls))
    unique_urls = list(dict.fromkeys(urls))
    if profiler is not None:
        profiler.set_counter("unique_url_count", len(unique_urls))

    url_infos: dict[str, UrlInfo] = {}
    for url in unique_urls:
        started = perf_counter()
        info = inspect_url_with_google(url, drive_config=drive_config)
        url_infos[url] = info
        if profiler is not None:
            profiler.record(
                "url_inspection",
                "url.inspect",
                perf_counter() - started,
                url=url,
                kind=info.kind,
                domain=info.domain,
                ok=info.error is None,
            )
    return url_infos


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
