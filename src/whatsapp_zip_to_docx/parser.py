from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


MESSAGE_RE = re.compile(
    r"^\u200e?\[(?P<date>\d{2}/\d{2}/\d{4}), (?P<time>\d{2}:\d{2}:\d{2})\] "
    r"(?P<author>.*?): (?P<body>.*)$"
)
ATTACHMENT_RE = re.compile(r"\u200e?<attached: (?P<filename>.+?)>$")
URL_RE = re.compile(r"https?://\S+")
EDITED_MARKER = "‎<This message was edited>"
ATTACHMENT_LABEL_RE = re.compile(
    r"^(?P<label>.+?)\s*•\s*(?P<details>\u200e?.+?)?$"
)
SKIPPED_BODIES = {
    "You deleted this message.",
    "This message was deleted.",
    "Messages and calls are end-to-end encrypted. Only people in this chat can read, listen to, or share them.",
}


@dataclass
class Attachment:
    filename: str
    path: Path


@dataclass
class Message:
    timestamp: datetime
    author: str
    body: str
    attachment: Optional[Attachment] = None
    urls: list[str] = field(default_factory=list)


def parse_chat(chat_text: str, attachments_dir: Path) -> list[Message]:
    messages: list[Message] = []
    current: Optional[Message] = None

    for raw_line in chat_text.splitlines():
        line = raw_line.rstrip("\r")
        match = MESSAGE_RE.match(line)
        if match:
            if current is not None:
                messages.append(current)

            timestamp = datetime.strptime(
                f"{match.group('date')} {match.group('time')}",
                "%d/%m/%Y %H:%M:%S",
            )
            body = _clean_body_text(match.group("body"))
            body, attachment = _extract_inline_attachment(body, attachments_dir)

            current = Message(
                timestamp=timestamp,
                author=match.group("author"),
                body=body,
                attachment=attachment,
                urls=_extract_urls(body),
            )
            if _should_skip_message(current):
                current = None
            continue

        if current is None:
            continue

        cleaned_line = _clean_body_text(line)
        current.body = f"{current.body}\n{cleaned_line}" if current.body else cleaned_line
        if current.attachment is None:
            current.body, current.attachment = _extract_inline_attachment(current.body, attachments_dir)
        current.urls = _extract_urls(current.body)

    if current is not None:
        messages.append(current)

    return messages


def _should_skip_message(message: Message) -> bool:
    if message.attachment is not None:
        return False
    cleaned = _normalize_system_text(message.body)
    return cleaned in SKIPPED_BODIES


def _clean_body_text(text: str) -> str:
    return text.replace(EDITED_MARKER, "").rstrip()


def _normalize_system_text(text: str) -> str:
    return text.strip().lstrip("\u200e").strip()


def _strip_attachment_label(text: str) -> str:
    candidate = text.strip().lstrip("\u200e").strip()
    if not candidate:
        return ""
    match = ATTACHMENT_LABEL_RE.match(candidate)
    if match:
        label = match.group("label").strip()
        if label:
            return label
        return ""
    return candidate


def _extract_inline_attachment(text: str, attachments_dir: Path) -> tuple[str, Optional[Attachment]]:
    attachment_match = ATTACHMENT_RE.search(text)
    if not attachment_match:
        return text, None
    filename = attachment_match.group("filename")
    attachment = Attachment(filename=filename, path=attachments_dir / filename)
    cleaned_text = _strip_attachment_label(text[: attachment_match.start()])
    return cleaned_text, attachment


def _extract_urls(text: str) -> list[str]:
    return [_clean_extracted_url(match.group(0)) for match in URL_RE.finditer(text)]


def _clean_extracted_url(url: str) -> str:
    cleaned = url.rstrip(".,;:!?")
    return _strip_unbalanced_trailing_brackets(cleaned)


def _strip_unbalanced_trailing_brackets(url: str) -> str:
    pairs = (("(", ")"), ("[", "]"), ("{", "}"))
    cleaned = url
    changed = True
    while changed and cleaned:
        changed = False
        for opener, closer in pairs:
            if cleaned.endswith(closer) and cleaned.count(closer) > cleaned.count(opener):
                cleaned = cleaned[:-1]
                changed = True
    return cleaned
