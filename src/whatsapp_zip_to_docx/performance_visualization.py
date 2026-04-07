from __future__ import annotations

from html import escape
import json
from pathlib import Path


WIDTH = 1400
HEIGHT = 1240
MARGIN_X = 44
CARD_GAP = 18
CARD_WIDTH = 310
CARD_HEIGHT = 96
BAR_WIDTH = 520
BAR_HEIGHT = 22
BAR_GAP = 14


def render_performance_svg(report: dict[str, object], title: str) -> str:
    counters = report.get("counters", {})
    stage_totals = [row for row in report.get("stage_totals", []) if row.get("task") != "generate_document"]
    url_by_kind = report.get("url_by_kind", [])[:8]
    slow_urls = report.get("slow_urls", [])[:6]
    slow_previews = report.get("slow_previews", [])[:6]
    preview_by_task = report.get("preview_by_task", [])[:4]

    wall_time = _find_total_seconds(report.get("stage_totals", []), "generate_document")
    url_time = _find_total_seconds(report.get("stage_totals", []), "url_enrichment")
    audio_time = _find_total_seconds(report.get("stage_totals", []), "audio_transcription")
    write_time = _find_total_seconds(report.get("stage_totals", []), "write_docx")

    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        _style_block(),
        f'<rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="#f4efe6"/>',
        f'<rect x="24" y="24" width="{WIDTH - 48}" height="{HEIGHT - 48}" rx="28" fill="#fffaf2" stroke="#d8cdb9" stroke-width="2"/>',
        _text(MARGIN_X, 72, "WhatsApp ZIP to DOCX Performance", cls="title"),
        _text(MARGIN_X, 104, escape(title), cls="subtitle"),
        _text(
            WIDTH - MARGIN_X,
            104,
            f"Generated at {escape(str(report.get('generated_at', 'n/a')))}",
            cls="small muted anchor-end",
        ),
    ]

    card_y = 134
    card_values = [
        ("Total run", _seconds_label(wall_time), "Full document generation"),
        ("URL enrichment", _seconds_label(url_time), "Network-bound metadata resolution"),
        ("Messages", str(counters.get("message_count", "n/a")), "Messages parsed from the ZIP"),
        ("Unique URLs", str(counters.get("unique_url_count", "n/a")), "Unique public links inspected"),
    ]
    for index, (label, value, note) in enumerate(card_values):
        x = MARGIN_X + index * (CARD_WIDTH + CARD_GAP)
        svg_parts.append(_card(x, card_y, CARD_WIDTH, CARD_HEIGHT, label, value, note))

    svg_parts.extend(
        _bar_section(
            x=MARGIN_X,
            y=270,
            title="Time By Stage",
            subtitle="Largest buckets in the full run",
            items=[
                (
                    _labelize_task(row.get("task", "unknown")),
                    float(row.get("total_seconds", 0.0)),
                    f"{float(row.get('total_seconds', 0.0)):.1f}s",
                )
                for row in stage_totals[:6]
            ],
            fill="#c96f4a",
        )
    )

    svg_parts.extend(
        _bar_section(
            x=WIDTH - MARGIN_X - 640,
            y=270,
            title="URL Time By Kind",
            subtitle="Where URL inspection spends its time",
            items=[
                (
                    f"{row.get('kind', 'unknown')} ({row.get('count', 0)})",
                    float(row.get("total_seconds", 0.0)),
                    f"{float(row.get('total_seconds', 0.0)):.1f}s",
                )
                for row in url_by_kind
            ],
            fill="#4f7c82",
        )
    )

    summary_y = 560
    summary_x = MARGIN_X
    breakdown = [
        ("Audio transcription", _seconds_label(audio_time)),
        ("DOCX writing", _seconds_label(write_time)),
        ("Preview web images", _seconds_label(_find_total_seconds(preview_by_task, "preview.web_image"))),
        ("Preview remote video", _seconds_label(_find_total_seconds(preview_by_task, "preview.remote_video"))),
    ]
    svg_parts.append(_panel(summary_x, summary_y, 400, 180, "Fast read"))
    svg_parts.append(_text(summary_x + 24, summary_y + 58, "What dominates this run?", cls="section-small"))
    for index, (label, value) in enumerate(breakdown):
        y = summary_y + 94 + index * 28
        svg_parts.append(_text(summary_x + 24, y, label, cls="body"))
        svg_parts.append(_text(summary_x + 370, y, value, cls="body strong anchor-end"))

    svg_parts.append(_panel(470, summary_y, WIDTH - 470 - MARGIN_X, 180, "Takeaway"))
    takeaway_lines = [
        "The bottleneck is not Word generation.",
        "Most time is spent before writing the DOCX, inside URL enrichment.",
        "YouTube is the biggest cumulative cost because there are many links.",
        "Dropbox is the worst per-link cost, especially shared videos.",
    ]
    for index, line in enumerate(takeaway_lines):
        svg_parts.append(_text(494, summary_y + 58 + index * 30, line, cls="body"))

    svg_parts.extend(
        _table_section(
            x=MARGIN_X,
            y=780,
            width=640,
            title="Slowest URLs",
            subtitle="Individual links with the highest inspection cost",
            rows=[
                (
                    f"{float(row.get('elapsed_seconds', 0.0)):.1f}s",
                    str(row.get("kind", "unknown")),
                    _shorten(str(row.get("url", "n/a")), 60),
                )
                for row in slow_urls
            ],
            col_widths=(90, 110, 410),
        )
    )

    svg_parts.extend(
        _table_section(
            x=720,
            y=780,
            width=WIDTH - 720 - MARGIN_X,
            title="Slowest Previews",
            subtitle="Preview rendering work after metadata is already known",
            rows=[
                (
                    f"{float(row.get('elapsed_seconds', 0.0)):.1f}s",
                    str(row.get("task", "unknown")).replace("preview.", ""),
                    _shorten(str(row.get("url", "n/a")), 48),
                )
                for row in slow_previews
            ],
            col_widths=(90, 150, 350),
        )
    )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def write_performance_svg(report_path: Path, svg_path: Path | None = None) -> Path:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    target = svg_path or report_path.with_suffix(".svg")
    svg = render_performance_svg(report, title=report_path.stem)
    target.write_text(svg, encoding="utf-8")
    return target


def _style_block() -> str:
    return """
<style>
  .title { font: 700 32px Georgia, 'Times New Roman', serif; fill: #2c241b; }
  .subtitle { font: 500 18px 'Avenir Next', Helvetica, Arial, sans-serif; fill: #7d6a58; }
  .section { font: 700 20px 'Avenir Next', Helvetica, Arial, sans-serif; fill: #2f3f40; }
  .section-small { font: 700 16px 'Avenir Next', Helvetica, Arial, sans-serif; fill: #2f3f40; }
  .body { font: 500 15px 'Avenir Next', Helvetica, Arial, sans-serif; fill: #40362b; }
  .body.strong { font-weight: 700; }
  .small { font: 500 12px 'Avenir Next', Helvetica, Arial, sans-serif; }
  .muted { fill: #8f7d6e; }
  .card-label { font: 600 14px 'Avenir Next', Helvetica, Arial, sans-serif; fill: #876f5d; }
  .card-value { font: 700 34px Georgia, 'Times New Roman', serif; fill: #2b241b; }
  .card-note { font: 500 13px 'Avenir Next', Helvetica, Arial, sans-serif; fill: #7a6a5d; }
  .anchor-end { text-anchor: end; }
</style>
""".strip()


def _card(x: int, y: int, width: int, height: int, label: str, value: str, note: str) -> str:
    return "\n".join(
        [
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="22" fill="#fff" stroke="#dfd2c0" stroke-width="1.5"/>',
            _text(x + 20, y + 28, label, cls="card-label"),
            _text(x + 20, y + 62, value, cls="card-value"),
            _text(x + 20, y + 84, note, cls="card-note"),
        ]
    )


def _panel(x: int, y: int, width: int, height: int, title: str) -> str:
    return "\n".join(
        [
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="22" fill="#fff" stroke="#dfd2c0" stroke-width="1.5"/>',
            _text(x + 24, y + 34, title, cls="section"),
        ]
    )


def _bar_section(x: int, y: int, title: str, subtitle: str, items: list[tuple[str, float, str]], fill: str) -> list[str]:
    width = 640
    height = 250
    parts = [_panel(x, y, width, height, title), _text(x + 24, y + 58, subtitle, cls="small muted")]
    max_value = max((value for _label, value, _display in items), default=1.0)
    bar_y = y + 88
    for label, value, display in items:
        ratio = 0 if max_value <= 0 else value / max_value
        bar_len = max(2, int(BAR_WIDTH * ratio))
        parts.append(_text(x + 24, bar_y + 16, label, cls="body"))
        parts.append(f'<rect x="{x + 24}" y="{bar_y + 24}" width="{BAR_WIDTH}" height="{BAR_HEIGHT}" rx="11" fill="#efe5d8"/>')
        parts.append(f'<rect x="{x + 24}" y="{bar_y + 24}" width="{bar_len}" height="{BAR_HEIGHT}" rx="11" fill="{fill}"/>')
        parts.append(_text(x + 24 + BAR_WIDTH + 56, bar_y + 40, display, cls="body strong anchor-end"))
        bar_y += BAR_HEIGHT + BAR_GAP + 18
    return parts


def _table_section(
    x: int,
    y: int,
    width: int,
    title: str,
    subtitle: str,
    rows: list[tuple[str, str, str]],
    col_widths: tuple[int, int, int],
) -> list[str]:
    row_height = 34
    height = 110 + row_height * len(rows)
    parts = [_panel(x, y, width, height, title), _text(x + 24, y + 58, subtitle, cls="small muted")]
    header_y = y + 92
    headers = ("Time", "Type", "URL")
    current_x = x + 24
    for header, col_width in zip(headers, col_widths):
        parts.append(_text(current_x, header_y, header, cls="small"))
        current_x += col_width
    parts.append(f'<line x1="{x + 24}" y1="{header_y + 12}" x2="{x + width - 24}" y2="{header_y + 12}" stroke="#ded4c5" stroke-width="1"/>')

    row_y = header_y + 36
    for time_text, kind_text, url_text in rows:
        parts.append(_text(x + 24, row_y, time_text, cls="body strong"))
        parts.append(_text(x + 24 + col_widths[0], row_y, kind_text, cls="body"))
        parts.append(_text(x + 24 + col_widths[0] + col_widths[1], row_y, url_text, cls="small"))
        parts.append(f'<line x1="{x + 24}" y1="{row_y + 12}" x2="{x + width - 24}" y2="{row_y + 12}" stroke="#efe7db" stroke-width="1"/>')
        row_y += row_height
    return parts


def _text(x: int, y: int, value: str, cls: str = "body") -> str:
    return f'<text x="{x}" y="{y}" class="{cls}">{escape(value)}</text>'


def _seconds_label(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}s"


def _find_total_seconds(rows: list[dict[str, object]], task: str) -> float | None:
    for row in rows:
        if row.get("task") == task:
            return float(row.get("total_seconds", 0.0))
    return None


def _labelize_task(task: str) -> str:
    return task.replace("_", " ")


def _shorten(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."
