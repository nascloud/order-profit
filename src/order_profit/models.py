"""领域结果、审计记录与错误数据结构。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class RunStatus(StrEnum):
    FAILED = "FAILED"
    PROVISIONAL = "PROVISIONAL"
    FINAL = "FINAL"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    file: str | None = None
    sheet: str | None = None
    row: int | None = None
    field: str | None = None


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    severity: Severity
    message: str
    location: SourceLocation = field(default_factory=SourceLocation)
    raw_value: Any = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["severity"] = self.severity.value
        return result


@dataclass(frozen=True, slots=True)
class InputFileMetadata:
    role: str
    path: Path
    sha256: str
    size_bytes: int
    rows: int | None = None
    sheet: str | None = None
    encoding: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["path"] = str(self.path.resolve())
        return result


@dataclass(slots=True)
class PipelineResult:
    """后续 P4～P13 共用的权威结果容器。"""

    status: RunStatus
    inputs: dict[str, InputFileMetadata] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    tables: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
