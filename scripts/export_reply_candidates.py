from __future__ import annotations

import argparse
from pathlib import Path

from whatsapp_zip_to_docx.parser import parse_chat
from whatsapp_zip_to_docx.reply_analysis import (
    render_candidates_markdown,
    semantic_scoring_candidates,
    simple_local_candidates,
)
from whatsapp_zip_to_docx.zip_reader import extract_zip


def main() -> int:
    parser = argparse.ArgumentParser(description="Export reply-link candidates from a WhatsApp zip.")
    parser.add_argument("input_zip", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    extracted = extract_zip(args.input_zip)
    try:
        messages = parse_chat(extracted.chat_file.read_text(encoding="utf-8"), extracted.root_dir)
    finally:
        extracted.temp_dir.cleanup()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    simple_path = args.output_dir / "reply_candidates_simple.md"
    semantic_path = args.output_dir / "reply_candidates_semantic.md"
    simple_path.write_text(
        render_candidates_markdown(
            messages,
            simple_local_candidates(messages),
            "Liens de reponse - heuristique locale simple",
        ),
        encoding="utf-8",
    )
    semantic_path.write_text(
        render_candidates_markdown(
            messages,
            semantic_scoring_candidates(messages),
            "Liens de reponse - scoring semantique",
        ),
        encoding="utf-8",
    )
    print(simple_path)
    print(semantic_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
