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
            body = match.group("body")
            body = _clean_body_text(body)
            attachment = None
            attachment_match = ATTACHMENT_RE.search(body)
            if attachment_match:
                filename = attachment_match.group("filename")
                attachment = Attachment(filename=filename, path=attachments_dir / filename)
                body = _strip_attachment_label(body[: attachment_match.start()])

            current = Message(
                timestamp=timestamp,
                author=match.group("author"),
                body=body,
                attachment=attachment,
                urls=URL_RE.findall(body),
            )
            if _should_skip_message(current):
                current = None
            continue

        if current is None:
            continue

        cleaned_line = _clean_body_text(line)
        current.body = f"{current.body}\n{cleaned_line}" if current.body else cleaned_line
        current.urls = URL_RE.findall(current.body)

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
