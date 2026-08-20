"""OrcaSlicerに依存しない診断出力I/Fと安全なJSON Lines出力。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
import json
from pathlib import Path
from threading import Lock
from typing import Protocol


class DiagnosticLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    level: DiagnosticLevel
    code: str
    message: str
    details: dict[str, object] = field(default_factory=dict)


class DiagnosticSink(Protocol):
    def emit(self, event: DiagnosticEvent) -> None: ...


class NullDiagnosticSink:
    def emit(self, event: DiagnosticEvent) -> None:
        return None


class MemoryDiagnosticSink:
    def __init__(self):
        self.events: list[DiagnosticEvent] = []

    def emit(self, event: DiagnosticEvent) -> None:
        self.events.append(event)


class ContextDiagnosticSink:
    def __init__(self, sink: DiagnosticSink, context: Mapping[str, object]):
        self._sink = sink
        self._context = dict(context)

    def emit(self, event: DiagnosticEvent) -> None:
        self._sink.emit(
            DiagnosticEvent(
                event.level,
                event.code,
                event.message,
                {**self._context, **event.details},
            )
        )


class SafeDiagnosticSink:
    def __init__(self, sink: DiagnosticSink):
        self._sink = sink

    def emit(self, event: DiagnosticEvent) -> None:
        try:
            self._sink.emit(event)
        except Exception:
            return None


_FILE_LOCK = Lock()


class JsonLinesDiagnosticSink:
    def __init__(self, path: Path, *, max_bytes: int = 5 * 1024 * 1024):
        if max_bytes < 1024:
            raise ValueError("max_bytes must be at least 1024")
        self._path = path
        self._max_bytes = max_bytes

    def emit(self, event: DiagnosticEvent) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": event.level.value,
            "code": event.code,
            "message": event.message,
            "details": event.details,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        encoded_bytes = len(line.encode("utf-8"))
        if encoded_bytes > self._max_bytes:
            record.update(
                {
                    "level": DiagnosticLevel.WARNING.value,
                    "code": "diagnostic_event_truncated",
                    "message": "診断イベントが上限を超えたため詳細を省略しました",
                    "details": {
                        "original_code": event.code,
                        "encoded_bytes": encoded_bytes,
                    },
                }
            )
            line = json.dumps(
                record, ensure_ascii=False, separators=(",", ":")
            ) + "\n"
        with _FILE_LOCK:
            mode = "a"
            try:
                if self._path.stat().st_size + len(line.encode("utf-8")) > self._max_bytes:
                    mode = "w"
            except FileNotFoundError:
                pass
            with self._path.open(mode, encoding="utf-8") as stream:
                stream.write(line)
