from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .parser import Message


AUDIO_EXTENSIONS = {".opus", ".ogg", ".mp3", ".m4a", ".aac", ".wav", ".amr"}
HIGH_ACCURACY_LANGUAGES = {"fr", "nl"}
_WHISPER_MODELS: dict[str, object] = {}


@dataclass(frozen=True)
class AudioTranscript:
    attachment_path: Path
    text: str | None = None
    language: str | None = None
    error: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.text and self.text.strip())


def is_supported_audio(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def collect_audio_attachments(messages: Iterable[Message]) -> list[Path]:
    seen: set[Path] = set()
    audio_paths: list[Path] = []
    for message in messages:
        attachment = message.attachment
        if attachment is None:
            continue
        if not is_supported_audio(attachment.path):
            continue
        if attachment.path in seen:
            continue
        seen.add(attachment.path)
        audio_paths.append(attachment.path)
    return audio_paths


def transcribe_audio_attachments(messages: Iterable[Message], model_name: str = "tiny") -> dict[Path, AudioTranscript]:
    transcripts: dict[Path, AudioTranscript] = {}
    for path in collect_audio_attachments(messages):
        transcripts[path] = transcribe_audio_file(path, model_name=model_name)
    return transcripts


def transcribe_audio_file(audio_path: Path, model_name: str = "tiny") -> AudioTranscript:
    try:
        whisper = _import_whisper()
        detected_language = _detect_language(whisper, audio_path)
        selected_model_name = _select_model_name(detected_language, default_model_name=model_name)
        model = _load_model(whisper, model_name=selected_model_name)
        transcribe_kwargs = {"fp16": False}
        if detected_language:
            transcribe_kwargs["language"] = detected_language
        result = model.transcribe(str(audio_path), **transcribe_kwargs)
    except Exception as exc:
        return AudioTranscript(
            attachment_path=audio_path,
            error=str(exc),
        )

    text = (result.get("text") or "").strip()
    language = result.get("language") or detected_language
    if not text:
        return AudioTranscript(
            attachment_path=audio_path,
            language=language,
            error="Transcription vide.",
        )
    return AudioTranscript(
        attachment_path=audio_path,
        text=text,
        language=language,
    )


def _import_whisper():
    import whisper  # type: ignore

    return whisper


def _detect_language(whisper, audio_path: Path) -> str | None:
    model = _load_model(whisper, model_name="tiny")
    audio = whisper.load_audio(str(audio_path))
    audio = whisper.pad_or_trim(audio)
    mel = whisper.log_mel_spectrogram(audio).to(model.device)
    _language, probabilities = model.detect_language(mel)
    if not probabilities:
        return None
    return max(probabilities, key=probabilities.get)


def _select_model_name(detected_language: str | None, default_model_name: str = "tiny") -> str:
    if detected_language in HIGH_ACCURACY_LANGUAGES:
        return "medium"
    return default_model_name


def _load_model(whisper, model_name: str = "tiny"):
    if model_name not in _WHISPER_MODELS:
        _WHISPER_MODELS[model_name] = whisper.load_model(model_name)
    return _WHISPER_MODELS[model_name]
