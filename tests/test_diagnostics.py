import json
from pathlib import Path
import tempfile
import unittest

from orcaslicer_hole_reinforcement.diagnostics import (
    ContextDiagnosticSink,
    DiagnosticEvent,
    DiagnosticLevel,
    JsonLinesDiagnosticSink,
    MemoryDiagnosticSink,
    SafeDiagnosticSink,
)


class FailingSink:
    def emit(self, event):
        raise OSError("read-only filesystem")


class DiagnosticsTests(unittest.TestCase):
    def test_writes_structured_json_lines_without_escaping_japanese(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.jsonl"
            sink = JsonLinesDiagnosticSink(path)

            sink.emit(
                DiagnosticEvent(
                    DiagnosticLevel.INFO,
                    "detected",
                    "穴を検出しました",
                    {"volume_id": 12},
                )
            )

            content = path.read_text(encoding="utf-8")
            record = json.loads(content)
            self.assertIn("穴を検出しました", content)
            self.assertEqual(record["code"], "detected")
            self.assertEqual(record["details"]["volume_id"], 12)
            self.assertTrue(record["timestamp"].endswith("+00:00"))

    def test_context_is_added_without_overwriting_event_details(self):
        memory = MemoryDiagnosticSink()
        sink = ContextDiagnosticSink(memory, {"object_id": 1, "volume_id": 2})

        sink.emit(
            DiagnosticEvent(
                DiagnosticLevel.WARNING,
                "excluded",
                "除外しました",
                {"volume_id": 3, "reason": "broken_mesh"},
            )
        )

        self.assertEqual(
            memory.events[0].details,
            {"object_id": 1, "volume_id": 3, "reason": "broken_mesh"},
        )

    def test_write_failure_is_suppressed(self):
        sink = SafeDiagnosticSink(FailingSink())

        sink.emit(DiagnosticEvent(DiagnosticLevel.ERROR, "write", "失敗"))

    def test_reuses_single_file_after_size_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.jsonl"
            sink = JsonLinesDiagnosticSink(path, max_bytes=1024)
            event = DiagnosticEvent(
                DiagnosticLevel.INFO,
                "large",
                "記録",
                {"payload": "x" * 800},
            )

            sink.emit(event)
            sink.emit(event)

            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 1)

    def test_replaces_oversized_event_with_bounded_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.jsonl"
            sink = JsonLinesDiagnosticSink(path, max_bytes=1024)

            sink.emit(
                DiagnosticEvent(
                    DiagnosticLevel.INFO,
                    "oversized",
                    "記録",
                    {"payload": "x" * 2048},
                )
            )

            content = path.read_bytes()
            record = json.loads(content)
            self.assertLessEqual(len(content), 1024)
            self.assertEqual(record["code"], "diagnostic_event_truncated")
            self.assertEqual(record["details"]["original_code"], "oversized")


if __name__ == "__main__":
    unittest.main()
