from __future__ import annotations

from pathlib import Path

from .app_model import AssistantState
from .app_session import DocumentSession
from .engine import EngineResult
from .google_drive import DriveConfig
from .profile_store import load_profiles, upsert_profile
from .profiles import UserProfile


def list_profiles() -> list[UserProfile]:
    return load_profiles()


def save_profile(profile: UserProfile) -> Path:
    return upsert_profile(profile)


def open_document_session(
    input_zip: Path,
    suggested_output_docx: Path | None = None,
    self_name: str = "Alain",
    other_initial: str = "M",
) -> DocumentSession:
    return DocumentSession.from_zip(
        input_zip=input_zip,
        suggested_output_docx=suggested_output_docx,
        self_name=self_name,
        other_initial=other_initial,
    )


def open_assistant_state(
    input_zip: Path,
    suggested_output_docx: Path | None = None,
    self_name: str = "Alain",
    other_initial: str = "M",
) -> AssistantState:
    session = open_document_session(
        input_zip=input_zip,
        suggested_output_docx=suggested_output_docx,
        self_name=self_name,
        other_initial=other_initial,
    )
    return AssistantState.from_session(session)


def run_document_session(
    session: DocumentSession,
    initials_by_author: dict[str, str] | None = None,
    drive_config: DriveConfig | None = None,
    write_performance_report: bool = True,
) -> EngineResult:
    return session.generate(
        initials_by_author=initials_by_author,
        drive_config=drive_config,
        write_performance_report=write_performance_report,
    )
