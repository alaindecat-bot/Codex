from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .app_session import DocumentSession, ParticipantSuggestion
from .engine import EngineRequest, EngineResult
from .google_drive import DriveConfig
from .profiles import UserProfile
from .timing_estimator import (
    DEFAULT_TIMEOUT_MULTIPLIER,
    TimingPrediction,
    estimate_timing,
    load_timing_history,
    summarize_workload,
)


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
    write_performance_report: bool = True
    timeout_mode: str = "multiplier"
    timeout_multiplier: float = DEFAULT_TIMEOUT_MULTIPLIER
    timeout_fixed_seconds: float = 900.0

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

    def with_performance_report(self, enabled: bool) -> "AssistantState":
        return replace(self, write_performance_report=enabled)

    def with_timeout_mode(self, timeout_mode: str) -> "AssistantState":
        normalized = timeout_mode if timeout_mode in {"multiplier", "fixed"} else "multiplier"
        return replace(self, timeout_mode=normalized)

    def with_timeout_multiplier(self, value: float) -> "AssistantState":
        return replace(self, timeout_multiplier=max(1.0, value))

    def with_timeout_fixed_seconds(self, value: float) -> "AssistantState":
        return replace(self, timeout_fixed_seconds=max(60.0, value))

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
            },
            write_performance_report=self.write_performance_report,
        )

    def generate(self, drive_config: DriveConfig | None = None) -> EngineResult:
        request = self.build_request()
        return self.session.with_profile(self.selected_profile_name).with_output(self.output_docx).generate(
            initials_by_author=request.initials_by_author,
            drive_config=drive_config,
            write_performance_report=request.write_performance_report,
        )

    def workload_prediction(self) -> TimingPrediction:
        history = load_timing_history()
        summary = summarize_workload(self.session.conversation.messages, self.selected_profile)
        return estimate_timing(summary, self.selected_profile, history=history)

    def timeout_seconds(self) -> float:
        prediction = self.workload_prediction()
        return prediction.timeout_seconds(self.timeout_mode, self.timeout_multiplier, self.timeout_fixed_seconds)


def participant_defaults(suggestions: list[ParticipantSuggestion]) -> list[ParticipantDraft]:
    return [
        ParticipantDraft(author_name=suggestion.author_name, initial=suggestion.suggested_initial)
        for suggestion in suggestions
    ]
