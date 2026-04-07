from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from whatsapp_zip_to_docx.engine import EngineRequest
from whatsapp_zip_to_docx.orchestrator import generate_document
from whatsapp_zip_to_docx.parser import Attachment, Message
from whatsapp_zip_to_docx.profiles import default_profile
from whatsapp_zip_to_docx.timing_estimator import (
    estimate_timing,
    guess_url_kind,
    summarize_workload,
)
from datetime import datetime


class TimingEstimatorTests(unittest.TestCase):
    def test_guess_url_kind_covers_major_services(self) -> None:
        self.assertEqual(guess_url_kind("https://youtu.be/abc"), "youtube")
        self.assertEqual(guess_url_kind("https://open.spotify.com/track/abc"), "spotify")
        self.assertEqual(guess_url_kind("https://docs.google.com/document/d/abc/edit"), "google_drive")
        self.assertEqual(guess_url_kind("https://www.dropbox.com/s/x/file.mp4?dl=0"), "dropbox")
        self.assertEqual(guess_url_kind("https://www.icloud.com/numbers/xyz"), "icloud")
        self.assertEqual(guess_url_kind("https://www.linkedin.com/posts/example"), "linkedin")
        self.assertEqual(guess_url_kind("https://www.swr.de/example.html"), "swr")
        self.assertEqual(guess_url_kind("https://teams.microsoft.com/l/meetup-join/abc"), "meeting")

    def test_estimate_timing_uses_message_and_url_counts(self) -> None:
        profile = default_profile()
        messages = [
            Message(
                timestamp=datetime(2026, 4, 3, 10, 0, 0),
                author="A",
                body="one https://youtu.be/abc",
                urls=["https://youtu.be/abc"],
            ),
            Message(
                timestamp=datetime(2026, 4, 3, 10, 1, 0),
                author="B",
                body="two https://www.dropbox.com/s/x/file.mp4?dl=0",
                urls=["https://www.dropbox.com/s/x/file.mp4?dl=0"],
                attachment=Attachment(filename="voice.m4a", path=Path("/tmp/voice.m4a")),
            ),
        ]

        summary = summarize_workload(messages, profile)
        prediction = estimate_timing(summary, profile, history=[])

        self.assertEqual(summary.message_count, 2)
        self.assertEqual(summary.unique_url_count, 2)
        self.assertEqual(summary.audio_attachment_count, 1)
        self.assertEqual(summary.url_kind_counts["youtube"], 1)
        self.assertEqual(summary.url_kind_counts["dropbox"], 1)
        self.assertGreater(prediction.total_seconds, 0.0)
        self.assertTrue(any(stage.key == "url_enrichment" for stage in prediction.stage_estimates))
        self.assertTrue(any(stage.key == "audio_transcription" for stage in prediction.stage_estimates))

    def test_generate_document_can_skip_performance_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            zip_path = temp_dir / "chat.zip"
            output_path = temp_dir / "output.docx"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(
                    "_chat.txt",
                    "[03/04/2026, 10:00:00] Alain: Bonjour\n[03/04/2026, 10:01:00] Bruno: Salut\n",
                )

            result = generate_document(
                EngineRequest(
                    input_zip=zip_path,
                    output_docx=output_path,
                    initials_by_author={"Alain": "A", "Bruno": "B"},
                    profile=default_profile(),
                    write_performance_report=False,
                )
            )

            self.assertTrue(output_path.exists())
            self.assertIsNone(result.performance_report_path)
            self.assertIsNone(result.performance_summary_path)
            self.assertIsNone(result.performance_svg_path)


if __name__ == "__main__":
    unittest.main()
