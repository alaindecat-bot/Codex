from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .parser import Message


@dataclass
class LaunchConfig:
    output_docx: Path
    initials_by_author: dict[str, str]
    include_summary: bool
    spotify_mode: str


def prompt_launch_config(
    input_zip: Path,
    default_output: Path,
    messages: list[Message],
) -> LaunchConfig:
    authors = list(dict.fromkeys(message.author for message in messages))
    print()
    print("Configuration du document")
    print("------------------------")
    output_docx = _prompt_path(
        "Nom du document Word",
        default_output,
    )
    initials_by_author = _prompt_author_initials(authors)
    include_summary = _prompt_yes_no("Inserer un resume en tete du document", default=True)
    spotify_mode = _prompt_choice(
        "Traitement des liens Spotify",
        default="simple",
        options={
            "simple": "Afficher seulement les metadonnees et 'Paroles trouvables: oui/non'",
            "poeme": "Reserver une place pour une integration ulterieure des paroles en format poeme",
        },
    )
    print()
    print(f"Fichier source: {input_zip}")
    print(f"Sortie: {output_docx}")
    print(f"Mode Spotify: {spotify_mode}")
    print()
    return LaunchConfig(
        output_docx=output_docx,
        initials_by_author=initials_by_author,
        include_summary=include_summary,
        spotify_mode=spotify_mode,
    )


def build_summary_lines(messages: list[Message], generated_at: datetime) -> list[str]:
    authors = list(dict.fromkeys(message.author for message in messages))
    start = messages[0].timestamp
    end = messages[-1].timestamp
    return [
        f"Participants: {', '.join(authors)}",
        f"Periode: du {start:%d/%m/%Y} au {end:%d/%m/%Y}",
        f"Genere le: {generated_at:%d/%m/%Y}",
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
