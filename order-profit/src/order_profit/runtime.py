"""日志初始化与运行清单生成。"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from order_profit import __version__
from order_profit.config import RunConfig, SPEC_VERSION
from order_profit.models import InputFileMetadata, Issue, RunStatus

LOGGER_NAME = "order_profit"


def configure_logging(*, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    return logger


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    *,
    config: RunConfig,
    status: RunStatus,
    inputs: dict[str, InputFileMetadata],
    issues: list[Issue] | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "spec_version": SPEC_VERSION,
        "program_version": __version__,
        "status": status.value,
        "started_at": (started_at or datetime.now(UTC)).isoformat(),
        "completed_at": (completed_at or datetime.now(UTC)).isoformat(),
        "config": config.to_dict(),
        "inputs": {name: metadata.to_dict() for name, metadata in inputs.items()},
        "issues": [issue.to_dict() for issue in (issues or [])],
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)
