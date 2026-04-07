from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re

from .engine import EngineRequest, EngineResult
from .google_drive import DriveConfig
from .orchestrator import PreparedConversation, build_initials_map, generate_document, prepare_conversation
from .profile_store import load_profiles
from .profiles import UserProfile, default_profile


@dataclass(frozen=True)
class ParticipantSuggestion:
    author_name: str
    suggested_initial: str


@dataclass(frozen=True)
class DocumentSession:
    input_zip: Path
    suggested_output_docx: Path
    conversation: PreparedConversation
    available_profiles: list[UserProfile]
    selected_profile: UserProfile
    participant_suggestions: list[ParticipantSuggestion]

    @classmethod
    def from_zip(
        cls,
        input_zip: Path,
        suggested_output_docx: Path | None = None,
        self_name: str = "Alain",
        other_initial: str = "M",
    ) -> "DocumentSession":
        conversation = prepare_conversation(input_zip)
        profiles = load_profiles()
        selected_profile = profiles[0] if profiles else default_profile()
        initials = build_initials_map(conversation.authors, self_name, other_initial)
        suggestions = [
            ParticipantSuggestion(author_name=author, suggested_initial=initials[author])
            for author in conversation.authors
        ]
        output_docx = suggested_output_docx or input_zip.with_name(_safe_output_name(input_zip))
        return cls(
            input_zip=input_zip,
            suggested_output_docx=output_docx,
            conversation=conversation,
            available_profiles=profiles or [selected_profile],
            selected_profile=selected_profile,
            participant_suggestions=suggestions,
        )

    def with_profile(self, profile_name: str) -> "DocumentSession":
        for profile in self.available_profiles:
            if profile.name == profile_name:
                return replace(self, selected_profile=profile)
        raise ValueError(f"Unknown profile: {profile_name}")

    def with_output(self, output_docx: Path) -> "DocumentSession":
        return replace(self, suggested_output_docx=output_docx)

    def build_request(
        self,
        initials_by_author: dict[str, str] | None = None,
        write_performance_report: bool = True,
    ) -> EngineRequest:
        resolved_initials = initials_by_author or {
            suggestion.author_name: suggestion.suggested_initial
            for suggestion in self.participant_suggestions
        }
        return EngineRequest(
            input_zip=self.input_zip,
            output_docx=self.suggested_output_docx,
            initials_by_author=resolved_initials,
            profile=self.selected_profile,
            write_performance_report=write_performance_report,
        )

    def generate(
        self,
        initials_by_author: dict[str, str] | None = None,
        drive_config: DriveConfig | None = None,
        write_performance_report: bool = True,
    ) -> EngineResult:
        request = self.build_request(
            initials_by_author=initials_by_author,
            write_performance_report=write_performance_report,
        )
        return generate_document(request, drive_config=drive_config)


def _safe_output_name(input_zip: Path) -> str:
    stem = input_zip.stem
    normalized = re.sub(r"[^A-Za-z0-9 _.-]+", "_", stem)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ._")
    if not normalized:
        normalized = "output"
    return f"{normalized}.docx"
