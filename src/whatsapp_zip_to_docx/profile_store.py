from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from .profiles import NetworkPolicy, UserProfile, default_profile


APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "WhatsAppZipToWord"
PROFILE_STORE_PATH = APP_SUPPORT_DIR / "profiles.json"


def default_profiles() -> list[UserProfile]:
    return [default_profile()]


def load_profiles(path: Path | None = None) -> list[UserProfile]:
    store_path = path or PROFILE_STORE_PATH
    if not store_path.exists():
        return default_profiles()
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_profiles()

    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list):
        return default_profiles()

    profiles: list[UserProfile] = []
    for item in raw_profiles:
        profile = _decode_profile(item)
        if profile is not None:
            profiles.append(profile)
    return profiles or default_profiles()


def save_profiles(profiles: list[UserProfile], path: Path | None = None) -> Path:
    store_path = path or PROFILE_STORE_PATH
    store_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"profiles": [_encode_profile(profile) for profile in profiles]}
    store_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return store_path


def upsert_profile(profile: UserProfile, path: Path | None = None) -> Path:
    profiles = load_profiles(path)
    updated: list[UserProfile] = []
    replaced = False
    for existing in profiles:
        if existing.name == profile.name:
            updated.append(profile)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        updated.append(profile)
    return save_profiles(updated, path)


def _encode_profile(profile: UserProfile) -> dict:
    return asdict(profile)


def _decode_profile(payload: object) -> UserProfile | None:
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    raw_network = payload.get("network", {})
    if not isinstance(raw_network, dict):
        raw_network = {}
    network = NetworkPolicy(
        assume_internet_access=bool(raw_network.get("assume_internet_access", True)),
        allow_google_drive=bool(raw_network.get("allow_google_drive", True)),
        allow_public_url_enrichment=bool(raw_network.get("allow_public_url_enrichment", True)),
    )
    return UserProfile(
        name=name,
        include_summary=bool(payload.get("include_summary", True)),
        spotify_mode=str(payload.get("spotify_mode", "poeme")),
        video_mode=str(payload.get("video_mode", "drive")),
        audio_transcription_enabled=bool(payload.get("audio_transcription_enabled", True)),
        enrich_public_urls=bool(payload.get("enrich_public_urls", True)),
        network=network,
    )
