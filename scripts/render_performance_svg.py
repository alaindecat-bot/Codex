from __future__ import annotations

import argparse
import json
from pathlib import Path

from whatsapp_zip_to_docx.performance_visualization import render_performance_svg


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a performance JSON report as an SVG dashboard.")
    parser.add_argument("input_json", type=Path, help="Path to a performance JSON file.")
    parser.add_argument("output_svg", type=Path, help="Path to the generated SVG dashboard.")
    args = parser.parse_args()

    report = json.loads(args.input_json.read_text(encoding="utf-8"))
    svg = render_performance_svg(report, title=args.input_json.stem)
    args.output_svg.write_text(svg, encoding="utf-8")
    print(args.output_svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
