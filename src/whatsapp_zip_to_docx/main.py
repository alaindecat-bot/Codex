from __future__ import annotations

import argparse
from pathlib import Path

from .engine import EngineRequest
from .google_drive import DriveConfig, ensure_drive_service, upload_file
from .interactive import prompt_launch_config
from .orchestrator import build_initials_map, generate_document, inspect_message_urls, prepare_conversation
from .profiles import UserProfile, default_profile


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

    prepared = prepare_conversation(args.input_zip)

    if args.interactive:
        launch = prompt_launch_config(args.input_zip, args.output_docx, prepared.messages)
        output_docx = launch.output_docx
        initials_by_author = launch.initials_by_author
        profile = launch.profile
    else:
        output_docx = args.output_docx
        initials_by_author = build_initials_map(prepared.authors, args.self_name, args.other_initial)
        profile = UserProfile(
            name="CLI run",
            include_summary=default_profile().include_summary,
            spotify_mode=default_profile().spotify_mode,
            video_mode="drive" if args.upload_videos_to_drive else "none",
            audio_transcription_enabled=default_profile().audio_transcription_enabled,
            enrich_public_urls=args.enrich_urls,
            network=default_profile().network,
        )

    if args.inspect_urls:
        url_infos = inspect_message_urls(prepared.messages)
        summarize_urls(url_infos)

    result = generate_document(
        EngineRequest(
            input_zip=args.input_zip,
            output_docx=output_docx,
            initials_by_author=initials_by_author,
            profile=profile,
        ),
        drive_config=drive_config,
    )

    for warning in result.warnings:
        print(f"Warning [{warning.code}]: {warning.message}")

    print(f"Wrote {result.output_docx}")
    return 0


def summarize_urls(url_infos) -> None:
    if not url_infos:
        print("No URLs found.")
        return

    print("URL summary:")
    for url, info in url_infos.items():
        print(f"- {info.kind}: {info.original_url} -> {info.final_url}")
        if info.kind == "spotify":
            print(f"  title: {info.spotify_title or 'n/a'}")
            print(
                "  lyrics_on_internet: yes"
                if info.lyrics_searchable
                else "  lyrics_on_internet: no"
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
