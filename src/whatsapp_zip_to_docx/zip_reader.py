from __future__ import annotations

import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractedChat:
    temp_dir: tempfile.TemporaryDirectory[str]
    root_dir: Path
    chat_file: Path


def extract_zip(zip_path: Path) -> ExtractedChat:
    temp_dir = tempfile.TemporaryDirectory(prefix="whatsapp_zip_to_docx_")
    root_dir = Path(temp_dir.name)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(root_dir)

    chat_candidates = sorted(root_dir.glob("*.txt"))
    if not chat_candidates:
        temp_dir.cleanup()
        raise FileNotFoundError("No .txt chat file found in zip archive.")

    return ExtractedChat(temp_dir=temp_dir, root_dir=root_dir, chat_file=chat_candidates[0])
