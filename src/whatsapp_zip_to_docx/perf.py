from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
import json
from pathlib import Path
from time import perf_counter
from typing import Iterator


@dataclass(frozen=True)
class PerformanceEvent:
    category: str
    task: str
    elapsed_seconds: float
    label: str | None = None
    url: str | None = None
    kind: str | None = None
    domain: str | None = None
    ok: bool = True


@dataclass
class PerformanceRecorder:
    events: list[PerformanceEvent] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)

    def set_counter(self, name: str, value: int) -> None:
        self.counters[name] = value

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount

    def record(
        self,
        category: str,
        task: str,
        elapsed_seconds: float,
        *,
        label: str | None = None,
        url: str | None = None,
        kind: str | None = None,
        domain: str | None = None,
        ok: bool = True,
    ) -> None:
        self.events.append(
            PerformanceEvent(
                category=category,
                task=task,
                elapsed_seconds=elapsed_seconds,
                label=label,
                url=url,
                kind=kind,
                domain=domain,
                ok=ok,
            )
        )

    @contextmanager
    def time(
        self,
        category: str,
        task: str,
        *,
        label: str | None = None,
        url: str | None = None,
        kind: str | None = None,
        domain: str | None = None,
    ) -> Iterator[None]:
        started = perf_counter()
        ok = True
        try:
            yield
        except Exception:
            ok = False
            raise
        finally:
            self.record(
                category,
                task,
                perf_counter() - started,
                label=label,
                url=url,
                kind=kind,
                domain=domain,
                ok=ok,
            )

    def report_dict(self, top_n: int = 10) -> dict[str, object]:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "counters": dict(sorted(self.counters.items())),
            "stage_totals": self._aggregate_by_task("stage"),
            "task_totals": self._aggregate_by_task(None),
            "url_by_kind": self._aggregate_url_field("kind"),
            "url_by_domain": self._aggregate_url_field("domain"),
            "preview_by_task": self._aggregate_preview_task(),
            "slow_urls": self._slow_events("url_inspection", top_n=top_n),
            "slow_previews": self._slow_events("preview", top_n=top_n),
            "events": [asdict(event) for event in self.events],
        }

    def summary_lines(self, top_n: int = 5) -> list[str]:
        report = self.report_dict(top_n=top_n)
        lines: list[str] = []
        wall_time = self._wall_time_seconds()
        if wall_time is not None:
            lines.append(f"Performance wall time: {wall_time:.1f}s.")
        if self.counters:
            counters = ", ".join(f"{name}={value}" for name, value in sorted(self.counters.items()))
            lines.append(f"Performance counters: {counters}.")

        stage_totals = report["stage_totals"]
        if isinstance(stage_totals, list) and stage_totals:
            stage_bits = "; ".join(
                f"{entry['task']} {entry['total_seconds']:.1f}s"
                for entry in stage_totals[:top_n]
            )
            lines.append(f"Performance stages: {stage_bits}.")

        url_by_kind = report["url_by_kind"]
        if isinstance(url_by_kind, list) and url_by_kind:
            kind_bits = "; ".join(
                f"{entry['kind']} {entry['count']} URL(s) in {entry['total_seconds']:.1f}s"
                for entry in url_by_kind[:top_n]
            )
            lines.append(f"URL time by kind: {kind_bits}.")

        slow_urls = report["slow_urls"]
        if isinstance(slow_urls, list) and slow_urls:
            url_bits = "; ".join(
                f"{entry['elapsed_seconds']:.1f}s [{entry['kind'] or 'unknown'}] {_shorten_url(entry['url'])}"
                for entry in slow_urls[:top_n]
            )
            lines.append(f"Slow URLs: {url_bits}.")

        slow_previews = report["slow_previews"]
        if isinstance(slow_previews, list) and slow_previews:
            preview_bits = "; ".join(
                f"{entry['elapsed_seconds']:.1f}s {entry['task']} {_shorten_url(entry['url'])}"
                for entry in slow_previews[:top_n]
            )
            lines.append(f"Slow previews: {preview_bits}.")

        return lines

    def write_json(self, path: Path, top_n: int = 15) -> None:
        payload = json.dumps(self.report_dict(top_n=top_n), indent=2, ensure_ascii=True)
        path.write_text(payload + "\n", encoding="utf-8")

    def write_text(self, path: Path, top_n: int = 10) -> None:
        path.write_text("\n".join(self.summary_lines(top_n=top_n)) + "\n", encoding="utf-8")

    def _aggregate_by_task(self, category: str | None) -> list[dict[str, object]]:
        totals: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)
        for event in self.events:
            if category is not None and event.category != category:
                continue
            totals[event.task] += event.elapsed_seconds
            counts[event.task] += 1
        rows = [
            {
                "task": task,
                "count": counts[task],
                "total_seconds": round(total, 6),
                "average_seconds": round(total / counts[task], 6),
            }
            for task, total in totals.items()
        ]
        return sorted(rows, key=lambda item: item["total_seconds"], reverse=True)

    def _aggregate_url_field(self, field_name: str) -> list[dict[str, object]]:
        totals: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)
        for event in self.events:
            if event.category != "url_inspection":
                continue
            key = getattr(event, field_name) or "unknown"
            totals[key] += event.elapsed_seconds
            counts[key] += 1
        rows = [
            {
                field_name: key,
                "count": counts[key],
                "total_seconds": round(total, 6),
                "average_seconds": round(total / counts[key], 6),
            }
            for key, total in totals.items()
        ]
        return sorted(rows, key=lambda item: item["total_seconds"], reverse=True)

    def _aggregate_preview_task(self) -> list[dict[str, object]]:
        totals: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)
        for event in self.events:
            if event.category != "preview":
                continue
            totals[event.task] += event.elapsed_seconds
            counts[event.task] += 1
        rows = [
            {
                "task": task,
                "count": counts[task],
                "total_seconds": round(total, 6),
                "average_seconds": round(total / counts[task], 6),
            }
            for task, total in totals.items()
        ]
        return sorted(rows, key=lambda item: item["total_seconds"], reverse=True)

    def _slow_events(self, category: str, top_n: int) -> list[dict[str, object]]:
        rows = [
            {
                "task": event.task,
                "elapsed_seconds": round(event.elapsed_seconds, 6),
                "url": event.url,
                "kind": event.kind,
                "domain": event.domain,
                "ok": event.ok,
            }
            for event in self.events
            if event.category == category
        ]
        rows.sort(key=lambda item: item["elapsed_seconds"], reverse=True)
        return rows[:top_n]

    def _wall_time_seconds(self) -> float | None:
        candidates = [
            event.elapsed_seconds
            for event in self.events
            if event.category == "stage" and event.task == "generate_document"
        ]
        if not candidates:
            return None
        return max(candidates)


def _shorten_url(url: str | None, max_length: int = 80) -> str:
    if not url:
        return "n/a"
    if len(url) <= max_length:
        return url
    return f"{url[: max_length - 3]}..."
