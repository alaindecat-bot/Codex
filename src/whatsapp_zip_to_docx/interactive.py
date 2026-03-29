from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .parser import Message
from .profile_store import load_profiles, upsert_profile
from .profiles import UserProfile, default_profile


@dataclass
class LaunchConfig:
    output_docx: Path
    initials_by_author: dict[str, str]
    profile: UserProfile


def prompt_launch_config(
    input_zip: Path,
    default_output: Path,
    messages: list[Message],
) -> LaunchConfig:
    stored_profiles = load_profiles()
    profile = _prompt_profile_selection(stored_profiles)
    authors = list(dict.fromkeys(message.author for message in messages))
    print()
    print("Configuration du document")
    print("------------------------")
    output_docx = _prompt_path(
        "Nom du document Word",
        default_output,
    )
    initials_by_author = _prompt_author_initials(authors)
    include_summary = _prompt_yes_no("Inserer un resume en tete du document", default=profile.include_summary)
    spotify_mode = _prompt_choice(
        "Traitement des liens Spotify",
        default=profile.spotify_mode,
        options={
            "simple": "Afficher seulement les metadonnees et 'Paroles trouvables: oui/non'",
            "poeme": "Utiliser le mode poeme par defaut quand le profil l'autorise",
        },
    )
    video_mode = _prompt_choice(
        "Traitement des videos",
        default=profile.video_mode,
        options={
            "drive": "Vignette cliquable avec upload automatique sur Google Drive",
            "local": "Vignette seule dans le document, sans lien cloud",
            "none": "Ne pas traiter specialement les videos",
        },
    )
    audio_transcription_enabled = _prompt_yes_no(
        "Transcrire les fichiers audio",
        default=profile.audio_transcription_enabled,
    )
    print()
    print(f"Fichier source: {input_zip}")
    print(f"Sortie: {output_docx}")
    selected_profile = UserProfile(
        name=profile.name,
        include_summary=include_summary,
        spotify_mode=spotify_mode,
        video_mode=video_mode,
        audio_transcription_enabled=audio_transcription_enabled,
        enrich_public_urls=profile.enrich_public_urls,
        network=profile.network,
    )
    print(f"Profil: {selected_profile.name}")
    print(f"Mode Spotify: {spotify_mode}")
    print(f"Mode video: {video_mode}")
    print(f"Transcription audio: {'oui' if audio_transcription_enabled else 'non'}")
    print()
    upsert_profile(selected_profile)
    return LaunchConfig(
        output_docx=output_docx,
        initials_by_author=initials_by_author,
        profile=selected_profile,
    )


def build_summary_lines(messages: list[Message], generated_at: datetime) -> list[str]:
    authors = list(dict.fromkeys(message.author for message in messages))
    start = messages[0].timestamp
    end = messages[-1].timestamp
    return [
        f"Participants: {', '.join(authors)}",
        f"Periode: du {start:%d/%m/%Y} au {end:%d/%m/%Y}",
        f"Généré le: {generated_at:%d/%m/%Y}",
    ]


def build_summary_lines_with_initials(
    messages: list[Message],
    generated_at: datetime,
    initials_by_author: dict[str, str],
) -> list[str]:
    authors = list(dict.fromkeys(message.author for message in messages))
    start = messages[0].timestamp
    end = messages[-1].timestamp
    participants = ", ".join(
        f"{author} ({initials_by_author.get(author, author[:1].upper())})"
        for author in authors
    )
    return [
        f"Participants: {participants}",
        f"Periode: du {start:%d/%m/%Y} au {end:%d/%m/%Y}",
        f"Généré le: {generated_at:%d/%m/%Y}",
    ]


def _prompt_author_initials(authors: list[str]) -> dict[str, str]:
    print()
    print("Participants")
    print("-----------")
    initials: dict[str, str] = {}
    for author in authors:
        default = author[:1].upper()
        value = input(f"Abreviation pour {author} [{default}]: ").strip()
        initials[author] = (value or default).upper()
    return initials


def _prompt_path(label: str, default: Path) -> Path:
    value = input(f"{label} [{default}]: ").strip()
    return Path(value).expanduser() if value else default


def _prompt_yes_no(label: str, default: bool) -> bool:
    hint = "O/n" if default else "o/N"
    value = input(f"{label} [{hint}]: ").strip().lower()
    if not value:
        return default
    return value in {"o", "oui", "y", "yes"}


def _prompt_choice(label: str, default: str, options: dict[str, str]) -> str:
    print(label)
    for key, description in options.items():
        marker = "*" if key == default else " "
        print(f"  {marker} {key}: {description}")
    value = input(f"Choix [{default}]: ").strip().lower()
    return value if value in options else default


def _prompt_profile_selection(profiles: list[UserProfile]) -> UserProfile:
    if not profiles:
        return default_profile()
    print()
    print("Profils")
    print("-------")
    for index, profile in enumerate(profiles, start=1):
        print(f"  {index}. {profile.name}")
    default_index = 1
    value = input(f"Profil a utiliser [{default_index}]: ").strip()
    try:
        selected_index = int(value) if value else default_index
    except ValueError:
        selected_index = default_index
    selected_index = min(max(selected_index, 1), len(profiles))
    selected = profiles[selected_index - 1]

    rename = input(f"Nom du profil a enregistrer [{selected.name}]: ").strip()
    if not rename:
        return selected
    return UserProfile(
        name=rename,
        include_summary=selected.include_summary,
        spotify_mode=selected.spotify_mode,
        video_mode=selected.video_mode,
        audio_transcription_enabled=selected.audio_transcription_enabled,
        enrich_public_urls=selected.enrich_public_urls,
        network=selected.network,
    )
