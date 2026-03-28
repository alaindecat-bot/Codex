from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .app_session import DocumentSession, ParticipantSuggestion
from .engine import EngineRequest, EngineResult
from .google_drive import DriveConfig
from .profiles import UserProfile


@dataclass(frozen=True)
class ParticipantDraft:
    author_name: str
    initial: str


@dataclass(frozen=True)
class AssistantState:
    session: DocumentSession
    output_docx: Path
    selected_profile_name: str
    participants: list[ParticipantDraft]

    @classmethod
    def from_session(cls, session: DocumentSession) -> "AssistantState":
        return cls(
            session=session,
            output_docx=session.suggested_output_docx,
            selected_profile_name=session.selected_profile.name,
            participants=[
                ParticipantDraft(
                    author_name=suggestion.author_name,
                    initial=suggestion.suggested_initial,
                )
                for suggestion in session.participant_suggestions
            ],
        )

    @property
    def available_profile_names(self) -> list[str]:
        return [profile.name for profile in self.session.available_profiles]

    @property
    def selected_profile(self) -> UserProfile:
        for profile in self.session.available_profiles:
            if profile.name == self.selected_profile_name:
                return profile
        return self.session.selected_profile

    def with_profile(self, profile_name: str) -> "AssistantState":
        updated_session = self.session.with_profile(profile_name)
        selected_profile = updated_session.selected_profile
        return replace(
            self,
            session=updated_session,
            selected_profile_name=selected_profile.name,
        )

    def with_output_docx(self, output_docx: Path) -> "AssistantState":
        updated_session = self.session.with_output(output_docx)
        return replace(
            self,
            session=updated_session,
            output_docx=output_docx,
        )

    def with_participant_initial(self, author_name: str, initial: str) -> "AssistantState":
        updated_participants = [
            replace(participant, initial=initial.upper())
            if participant.author_name == author_name
            else participant
            for participant in self.participants
        ]
        return replace(self, participants=updated_participants)

    def build_request(self) -> EngineRequest:
        return self.session.with_profile(self.selected_profile_name).with_output(self.output_docx).build_request(
            initials_by_author={
                participant.author_name: participant.initial
                for participant in self.participants
            }
        )

    def generate(self, drive_config: DriveConfig | None = None) -> EngineResult:
        request = self.build_request()
        return self.session.with_profile(self.selected_profile_name).with_output(self.output_docx).generate(
            initials_by_author=request.initials_by_author,
            drive_config=drive_config,
        )


def participant_defaults(suggestions: list[ParticipantSuggestion]) -> list[ParticipantDraft]:
    return [
        ParticipantDraft(author_name=suggestion.author_name, initial=suggestion.suggested_initial)
        for suggestion in suggestions
    ]
