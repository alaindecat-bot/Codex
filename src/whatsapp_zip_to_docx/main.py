from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import mimetypes
from pathlib import Path

from .docx_writer import write_docx
from .google_drive import DriveConfig, ensure_drive_service, upload_file
from .interactive import build_summary_lines, prompt_launch_config
from .parser import parse_chat
from .url_tools import UrlInfo, inspect_url
from .zip_reader import extract_zip


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a WhatsApp export zip to a Word document.")
    parser.add_argument("input_zip", type=Path, help="Path to the WhatsApp export zip file.")
    parser.add_argument("output_docx", type=Path, help="Path to the generated .docx file.")
    parser.add_argument(
        "--self-name",
        default="Alain",
        help="Display name to map to initial A.",
    )
    parser.add_argument(
        "--other-initial",
        default="M",
        help="Initial to use for the other participant.",
    )
    parser.add_argument(
        "--inspect-urls",
        action="store_true",
        help="Resolve URLs and print a summary to stdout.",
    )
    parser.add_argument(
        "--enrich-urls",
        action="store_true",
        help="Fetch public metadata for URLs and include supported details in the docx.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for participant abbreviations, output name, summary, and Spotify mode before generation.",
    )
    parser.add_argument(
        "--test-drive-auth",
        action="store_true",
        help="Run the Google Drive OAuth flow and validate local credentials.",
    )
    parser.add_argument(
        "--upload-to-drive",
        type=Path,
        help="Upload a file to the configured Google Drive folder and print the resulting link.",
    )
    parser.add_argument(
        "--upload-videos-to-drive",
        action="store_true",
        help="Upload video attachments to Google Drive and use clickable thumbnails in the generated docx.",
    )
    args = parser.parse_args()

    drive_config = DriveConfig(
        credentials_path=Path("secrets/client_secret_819489726933-ku0rotlcdumi2nphpfoqquun51krl2ah.apps.googleusercontent.com.json"),
        token_path=Path("secrets/google_drive_token.json"),
    )

    if args.test_drive_auth:
        ensure_drive_service(drive_config)
        print("Google Drive authentication OK.")
        return 0

    if args.upload_to_drive:
        link = upload_file(args.upload_to_drive, drive_config)
        print(link)
        return 0

    extracted = extract_zip(args.input_zip)
    try:
        chat_text = extracted.chat_file.read_text(encoding="utf-8")
        messages = parse_chat(chat_text, extracted.root_dir)
        authors = [message.author for message in messages]
        summary_lines: list[str] | None = None

        if args.interactive:
            launch = prompt_launch_config(args.input_zip, args.output_docx, messages)
            output_docx = launch.output_docx
            initials_by_author = launch.initials_by_author
            if launch.include_summary:
                summary_lines = build_summary_lines(messages, datetime.now())
            if launch.spotify_mode == "poeme":
                print("Note: le mode Spotify 'poeme' est prepare dans le dialogue, mais l'integration automatique des paroles reste a implementer.")
        else:
            output_docx = args.output_docx
            initials_by_author = build_initials_map(authors, args.self_name, args.other_initial)

        url_infos = inspect_message_urls(messages) if (args.inspect_urls or args.enrich_urls) else {}

        if args.inspect_urls:
            summarize_urls(url_infos)

        attachment_links: dict[Path, str] = {}
        if args.upload_videos_to_drive:
            attachment_links = upload_video_attachments(messages, drive_config)

        write_docx(
            output_docx,
            messages,
            initials_by_author,
            url_infos=url_infos if args.enrich_urls else None,
            summary_lines=summary_lines,
            attachment_links=attachment_links,
        )
    finally:
        extracted.temp_dir.cleanup()

    print(f"Wrote {output_docx}")
    return 0


def upload_video_attachments(messages: list, drive_config: DriveConfig) -> dict[Path, str]:
    links: dict[Path, str] = {}
    for message in messages:
        attachment = getattr(message, "attachment", None)
        if attachment is None:
            continue
        if attachment.path in links:
            continue
        if attachment.path.suffix.lower() not in {".mp4", ".mov", ".m4v"}:
            continue
        mime_type, _ = mimetypes.guess_type(str(attachment.path))
        links[attachment.path] = upload_file(attachment.path, drive_config, mime_type=mime_type)
    return links


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


def inspect_message_urls(messages: list) -> dict[str, UrlInfo]:
    urls: list[str] = []
    for message in messages:
        urls.extend(message.urls)
    unique_urls = list(dict.fromkeys(urls))
    return {url: inspect_url(url) for url in unique_urls}


def summarize_urls(url_infos: dict[str, UrlInfo]) -> None:
    if not url_infos:
        print("No URLs found.")
        return

    print("URL summary:")
    for url, info in url_infos.items():
        print(f"- {info.kind}: {info.original_url} -> {info.final_url}")
        if info.kind == "spotify":
            print(f"  title: {info.og_title or info.page_title or 'n/a'}")
            print(
                "  lyrics_on_internet: likely yes"
                if info.lyrics_searchable
                else "  lyrics_on_internet: unclear"
            )
        elif info.kind == "facebook":
            print(f"  title: {info.og_title or info.page_title or 'n/a'}")
            print(
                "  image_copyable_to_word: likely yes"
                if info.can_embed_post_image
                else "  image_copyable_to_word: no"
            )


if __name__ == "__main__":
    raise SystemExit(main())
