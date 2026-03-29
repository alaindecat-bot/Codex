from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NetworkPolicy:
    assume_internet_access: bool = True
    allow_google_drive: bool = True
    allow_public_url_enrichment: bool = True


@dataclass(frozen=True)
class UserProfile:
    name: str
    include_summary: bool = True
    spotify_mode: str = "poeme"
    video_mode: str = "drive"
    audio_transcription_enabled: bool = True
    enrich_public_urls: bool = True
    network: NetworkPolicy = field(default_factory=NetworkPolicy)

    def supports_drive_uploads(self) -> bool:
        return self.video_mode == "drive" and self.network.allow_google_drive


def default_profile(name: str = "Standard macOS") -> UserProfile:
    return UserProfile(name=name)
