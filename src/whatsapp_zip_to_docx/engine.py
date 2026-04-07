from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .profiles import UserProfile


@dataclass(frozen=True)
class EngineRequest:
    input_zip: Path
    output_docx: Path
    initials_by_author: dict[str, str]
    profile: UserProfile
    write_performance_report: bool = True


@dataclass(frozen=True)
class EngineWarning:
    code: str
    message: str


@dataclass(frozen=True)
class EngineResult:
    output_docx: Path
    warnings: list[EngineWarning] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    performance_report_path: Path | None = None
    performance_summary_path: Path | None = None
    performance_svg_path: Path | None = None


class DocumentEngine(Protocol):
    def generate(self, request: EngineRequest) -> EngineResult:
        ...
