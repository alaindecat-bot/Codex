from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
from urllib.parse import urlparse

from .parser import Message
from .profile_store import APP_SUPPORT_DIR
from .profiles import UserProfile


TIMING_HISTORY_PATH = APP_SUPPORT_DIR / "timing_history.json"
DEFAULT_TIMEOUT_MULTIPLIER = 2.0

DEFAULT_URL_SECONDS_BY_KIND = {
    "youtube": 1.45,
    "webpage": 0.75,
    "dropbox": 12.2,
    "google_drive": 4.15,
    "spotify": 1.32,
    "icloud": 7.55,
    "linkedin": 1.2,
    "x": 0.7,
    "swr": 1.0,
    "meeting": 0.27,
    "dubb": 0.68,
    "unknown": 0.45,
}
DEFAULT_PREVIEW_SECONDS_BY_KIND = {
    "youtube": 0.25,
    "webpage": 0.15,
    "dropbox": 3.5,
    "google_drive": 0.4,
    "spotify": 0.0,
    "icloud": 1.8,
    "linkedin": 0.25,
    "x": 0.1,
    "swr": 0.3,
    "meeting": 0.0,
    "dubb": 0.4,
    "unknown": 0.1,
}


@dataclass(frozen=True)
class WorkloadSummary:
    message_count: int
    unique_url_count: int
    url_mentions: int
    audio_attachment_count: int
    video_attachment_count: int
    visual_attachment_count: int
    url_kind_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class StageEstimate:
    key: str
    label: str
    predicted_seconds: float
    detail: str


@dataclass(frozen=True)
class TimingPrediction:
    summary: WorkloadSummary
    stage_estimates: list[StageEstimate]
    total_seconds: float

    def timeout_seconds(self, mode: str, multiplier: float, fixed_seconds: float) -> float:
        if mode == "fixed":
            return max(60.0, fixed_seconds)
        return max(60.0, self.total_seconds * max(1.0, multiplier))


@dataclass(frozen=True)
class RunHistoryEntry:
    created_at: str
    summary: WorkloadSummary
    predicted_total_seconds: float
    actual_total_seconds: float
    stage_seconds: dict[str, float]
    url_kind_seconds: dict[str, float]


@dataclass(frozen=True)
class PredictionComparison:
    status: str
    predicted_total_seconds: float
    actual_total_seconds: float
    timeout_seconds: float | None
    stage_rows: list[dict[str, float | str]]

    def summary_lines(self) -> list[str]:
        lines = [
            f"Outcome: {self.status}",
            f"Predicted total: {self.predicted_total_seconds:.1f}s",
            f"Actual total: {self.actual_total_seconds:.1f}s",
        ]
        if self.timeout_seconds is not None:
            lines.append(f"Timeout threshold: {self.timeout_seconds:.1f}s")
        lines.append("")
        lines.append("Stage comparison:")
        for row in self.stage_rows:
            lines.append(
                f"- {row['label']}: predicted {float(row['predicted_seconds']):.1f}s, "
                f"actual {float(row['actual_seconds']):.1f}s, delta {float(row['delta_seconds']):+.1f}s"
            )
        return lines


def summarize_workload(messages: list[Message], profile: UserProfile) -> WorkloadSummary:
    urls: list[str] = []
    audio_count = 0
    video_count = 0
    visual_count = 0
    for message in messages:
        urls.extend(message.urls)
        attachment = message.attachment
        if attachment is None:
            continue
        suffix = attachment.path.suffix.lower()
        if suffix in {".m4a", ".mp3", ".wav", ".ogg", ".opus", ".aac"} and profile.audio_transcription_enabled:
            audio_count += 1
        elif suffix in {".mp4", ".mov", ".m4v"}:
            video_count += 1
        elif suffix in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".pdf"}:
            visual_count += 1

    unique_urls = list(dict.fromkeys(urls))
    kind_counts: dict[str, int] = {}
    for url in unique_urls:
        kind = guess_url_kind(url)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    return WorkloadSummary(
        message_count=len(messages),
        unique_url_count=len(unique_urls),
        url_mentions=len(urls),
        audio_attachment_count=audio_count,
        video_attachment_count=video_count,
        visual_attachment_count=visual_count,
        url_kind_counts=kind_counts,
    )


def estimate_timing(summary: WorkloadSummary, profile: UserProfile, history: list[RunHistoryEntry] | None = None) -> TimingPrediction:
    url_costs = effective_url_seconds_by_kind(history)
    preview_costs = effective_preview_seconds_by_kind(history)

    url_enrichment_seconds = 0.0
    preview_seconds = 0.0
    if profile.enrich_public_urls and profile.network.allow_public_url_enrichment:
        for kind, count in summary.url_kind_counts.items():
            url_enrichment_seconds += url_costs.get(kind, url_costs["unknown"]) * count
            preview_seconds += preview_costs.get(kind, preview_costs["unknown"]) * count

    upload_seconds = 0.0
    if profile.supports_drive_uploads() and summary.video_attachment_count:
        upload_seconds = 6.0 * summary.video_attachment_count

    audio_seconds = 0.0
    if profile.audio_transcription_enabled:
        audio_seconds = 16.0 * summary.audio_attachment_count

    write_seconds = (
        2.0
        + 0.01 * summary.message_count
        + 0.5 * summary.visual_attachment_count
        + 0.8 * summary.video_attachment_count
        + preview_seconds
    )
    reply_seconds = max(0.15, 0.00035 * summary.message_count)
    preparation_seconds = 0.25 + 0.0002 * summary.message_count

    stages = [
        StageEstimate("prepare", "Preparation", round(preparation_seconds, 2), "ZIP extraction, chat read, parsing"),
        StageEstimate("url_enrichment", "URL enrichment", round(url_enrichment_seconds, 2), _kind_breakdown_detail(summary.url_kind_counts)),
        StageEstimate("drive_upload", "Drive uploads", round(upload_seconds, 2), f"{summary.video_attachment_count} video(s)"),
        StageEstimate("audio_transcription", "Audio transcription", round(audio_seconds, 2), f"{summary.audio_attachment_count} audio file(s)"),
        StageEstimate("reply_analysis", "Reply analysis", round(reply_seconds, 2), f"{summary.message_count} message(s)"),
        StageEstimate("write_docx", "DOCX writing", round(write_seconds, 2), "Document rendering and previews"),
    ]
    filtered_stages = [stage for stage in stages if stage.predicted_seconds > 0.0]
    total_seconds = round(sum(stage.predicted_seconds for stage in filtered_stages), 2)
    return TimingPrediction(summary=summary, stage_estimates=filtered_stages, total_seconds=total_seconds)


def load_timing_history(path: Path | None = None) -> list[RunHistoryEntry]:
    history_path = path or TIMING_HISTORY_PATH
    if not history_path.exists():
        return []
    try:
        payload = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), list):
        return []
    runs: list[RunHistoryEntry] = []
    for item in payload["runs"]:
        try:
            summary_payload = item["summary"]
            summary = WorkloadSummary(
                message_count=int(summary_payload["message_count"]),
                unique_url_count=int(summary_payload["unique_url_count"]),
                url_mentions=int(summary_payload["url_mentions"]),
                audio_attachment_count=int(summary_payload["audio_attachment_count"]),
                video_attachment_count=int(summary_payload["video_attachment_count"]),
                visual_attachment_count=int(summary_payload["visual_attachment_count"]),
                url_kind_counts={str(key): int(value) for key, value in summary_payload.get("url_kind_counts", {}).items()},
            )
            runs.append(
                RunHistoryEntry(
                    created_at=str(item["created_at"]),
                    summary=summary,
                    predicted_total_seconds=float(item["predicted_total_seconds"]),
                    actual_total_seconds=float(item["actual_total_seconds"]),
                    stage_seconds={str(k): float(v) for k, v in item.get("stage_seconds", {}).items()},
                    url_kind_seconds={str(k): float(v) for k, v in item.get("url_kind_seconds", {}).items()},
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return runs


def append_timing_history(entry: RunHistoryEntry, path: Path | None = None) -> Path:
    history_path = path or TIMING_HISTORY_PATH
    existing = load_timing_history(history_path)
    runs = existing[-49:] + [entry]
    payload = {"runs": [_encode_history_entry(run) for run in runs]}
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return history_path


def comparison_from_performance_report(
    prediction: TimingPrediction,
    performance_report_path: Path,
    *,
    status: str = "completed",
    timeout_seconds: float | None = None,
) -> PredictionComparison:
    payload = json.loads(performance_report_path.read_text(encoding="utf-8"))
    stage_totals = {str(row["task"]): float(row["total_seconds"]) for row in payload.get("stage_totals", [])}
    actual_total = stage_totals.get("generate_document", 0.0)
    mapping = {
        "prepare": ["extract_zip", "read_chat_text", "parse_chat", "build_summary"],
        "url_enrichment": ["url_enrichment"],
        "drive_upload": ["upload_video_attachments"],
        "audio_transcription": ["audio_transcription"],
        "reply_analysis": ["reply_analysis"],
        "write_docx": ["write_docx"],
    }
    rows: list[dict[str, float | str]] = []
    for stage in prediction.stage_estimates:
        actual_seconds = sum(stage_totals.get(task, 0.0) for task in mapping.get(stage.key, []))
        rows.append(
            {
                "key": stage.key,
                "label": stage.label,
                "predicted_seconds": stage.predicted_seconds,
                "actual_seconds": round(actual_seconds, 2),
                "delta_seconds": round(actual_seconds - stage.predicted_seconds, 2),
            }
        )
    return PredictionComparison(
        status=status,
        predicted_total_seconds=prediction.total_seconds,
        actual_total_seconds=round(actual_total, 2),
        timeout_seconds=timeout_seconds,
        stage_rows=rows,
    )


def comparison_for_interrupted_run(
    prediction: TimingPrediction,
    *,
    status: str,
    elapsed_seconds: float,
    timeout_seconds: float | None = None,
) -> PredictionComparison:
    rows = [
        {
            "key": stage.key,
            "label": stage.label,
            "predicted_seconds": stage.predicted_seconds,
            "actual_seconds": 0.0,
            "delta_seconds": round(-stage.predicted_seconds, 2),
        }
        for stage in prediction.stage_estimates
    ]
    return PredictionComparison(
        status=status,
        predicted_total_seconds=prediction.total_seconds,
        actual_total_seconds=round(elapsed_seconds, 2),
        timeout_seconds=timeout_seconds,
        stage_rows=rows,
    )


def write_prediction_comparison(comparison: PredictionComparison, output_path: Path) -> Path:
    output_path.write_text("\n".join(comparison.summary_lines()) + "\n", encoding="utf-8")
    return output_path


def make_history_entry(
    prediction: TimingPrediction,
    performance_report_path: Path,
) -> RunHistoryEntry:
    payload = json.loads(performance_report_path.read_text(encoding="utf-8"))
    stage_seconds = {
        str(row["task"]): float(row["total_seconds"])
        for row in payload.get("stage_totals", [])
    }
    url_kind_seconds = {
        str(row["kind"]): float(row["total_seconds"])
        for row in payload.get("url_by_kind", [])
    }
    return RunHistoryEntry(
        created_at=datetime.now(UTC).isoformat(),
        summary=prediction.summary,
        predicted_total_seconds=prediction.total_seconds,
        actual_total_seconds=stage_seconds.get("generate_document", 0.0),
        stage_seconds=stage_seconds,
        url_kind_seconds=url_kind_seconds,
    )


def effective_url_seconds_by_kind(history: list[RunHistoryEntry] | None) -> dict[str, float]:
    costs = dict(DEFAULT_URL_SECONDS_BY_KIND)
    if not history:
        return costs
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for run in history[-12:]:
        for kind, total_seconds in run.url_kind_seconds.items():
            count = run.summary.url_kind_counts.get(kind, 0)
            if count <= 0:
                continue
            totals[kind] = totals.get(kind, 0.0) + total_seconds
            counts[kind] = counts.get(kind, 0) + count
    for kind, total in totals.items():
        count = counts.get(kind, 0)
        if count > 0:
            observed = total / count
            default = costs.get(kind, costs["unknown"])
            costs[kind] = round((default + observed) / 2, 4)
    return costs


def effective_preview_seconds_by_kind(history: list[RunHistoryEntry] | None) -> dict[str, float]:
    return dict(DEFAULT_PREVIEW_SECONDS_BY_KIND)


def guess_url_kind(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host.split(":", 1)[0]
    if host in {"youtube.com", "www.youtube.com", "youtu.be"} or host.endswith(".youtube.com"):
        return "youtube"
    if host == "open.spotify.com" or host.endswith(".spotify.com"):
        return "spotify"
    if host == "dubb.com" or host.endswith(".dubb.com"):
        return "dubb"
    if host in {"docs.google.com", "drive.google.com"}:
        return "google_drive"
    if host == "dropbox.com" or host.endswith(".dropbox.com"):
        return "dropbox"
    if host == "icloud.com" or host.endswith(".icloud.com"):
        return "icloud"
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "linkedin"
    if host == "swr.de" or host.endswith(".swr.de"):
        return "swr"
    if any(
        host == domain or host.endswith(f".{domain}")
        for domain in (
            "teams.microsoft.com",
            "teams.live.com",
            "zoom.us",
            "meet.google.com",
            "webex.com",
            "calendly.com",
            "cal.com",
            "whereby.com",
            "doodle.com",
            "meet.jit.si",
        )
    ):
        return "meeting"
    return "webpage"


def format_prediction_summary(prediction: TimingPrediction, timeout_seconds: float) -> str:
    lines = [
        f"Estimation totale : {prediction.total_seconds:.1f}s",
        f"Timeout propose : {timeout_seconds:.1f}s",
    ]
    for stage in prediction.stage_estimates:
        lines.append(f"- {stage.label}: {stage.predicted_seconds:.1f}s ({stage.detail})")
    return "\n".join(lines)


def _kind_breakdown_detail(kind_counts: dict[str, int]) -> str:
    if not kind_counts:
        return "No public URLs"
    parts = [f"{kind}={count}" for kind, count in sorted(kind_counts.items())]
    return ", ".join(parts)


def _encode_history_entry(entry: RunHistoryEntry) -> dict[str, object]:
    payload = asdict(entry)
    payload["summary"] = asdict(entry.summary)
    return payload
