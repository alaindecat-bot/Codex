from __future__ import annotations

import unittest

from whatsapp_zip_to_docx.perf import PerformanceRecorder


class PerformanceRecorderTests(unittest.TestCase):
    def test_report_aggregates_url_and_preview_timings(self) -> None:
        recorder = PerformanceRecorder()
        recorder.set_counter("message_count", 42)
        recorder.record("stage", "generate_document", 12.5)
        recorder.record(
            "url_inspection",
            "url.inspect",
            2.0,
            url="https://youtu.be/example",
            kind="youtube",
            domain="youtu.be",
        )
        recorder.record(
            "url_inspection",
            "url.inspect",
            3.5,
            url="https://dropbox.com/s/example.mp4",
            kind="dropbox",
            domain="dropbox.com",
        )
        recorder.record(
            "preview",
            "preview.remote_video",
            4.25,
            url="https://dropbox.com/s/example.mp4",
            kind="dropbox",
            domain="dropbox.com",
            ok=False,
        )

        report = recorder.report_dict(top_n=3)

        self.assertEqual(report["counters"]["message_count"], 42)
        self.assertEqual(report["stage_totals"][0]["task"], "generate_document")
        self.assertEqual(report["url_by_kind"][0]["kind"], "dropbox")
        self.assertEqual(report["url_by_kind"][0]["count"], 1)
        self.assertEqual(report["slow_urls"][0]["url"], "https://dropbox.com/s/example.mp4")
        self.assertEqual(report["preview_by_task"][0]["task"], "preview.remote_video")
        self.assertFalse(report["slow_previews"][0]["ok"])

    def test_summary_lines_include_key_sections(self) -> None:
        recorder = PerformanceRecorder()
        recorder.record("stage", "generate_document", 9.0)
        recorder.record(
            "url_inspection",
            "url.inspect",
            1.5,
            url="https://example.com/article",
            kind="webpage",
            domain="example.com",
        )

        summary = recorder.summary_lines(top_n=3)

        self.assertTrue(any(line.startswith("Performance wall time:") for line in summary))
        self.assertTrue(any(line.startswith("URL time by kind:") for line in summary))
        self.assertTrue(any(line.startswith("Slow URLs:") for line in summary))


if __name__ == "__main__":
    unittest.main()
