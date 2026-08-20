"""OrcaSlicerに依存しない診断出力I/F。"""

from dataclasses import dataclass, field
from enum import Enum
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

