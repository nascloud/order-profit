"""正式输出事务：临时目录写入、验证后原子发布。"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from order_profit.config import RunConfig
from order_profit.errors import OutputError, ReconciliationError
from order_profit.excel_report import write_excel
from order_profit.html_report import write_html
from order_profit.pipeline import ValidationResult
from order_profit.runtime import (
    build_manifest,
    serialize_reconciliation,
    serialize_summary,
    write_manifest,
)
from order_profit.supplement_report import write_pending_supplements


@dataclass(frozen=True, slots=True)
class PublishedReports:
    excel: Path
    html: Path
    manifest: Path
    pending_supplements: Path | None = None


@dataclass(frozen=True, slots=True)
class RunOutcome:
    result: ValidationResult
    reports: PublishedReports


def execute_run(config: RunConfig) -> RunOutcome:
    """统一执行核算、完整性门禁和事务式报告发布。"""

    from order_profit.pipeline import validate_and_partition_orders

    result = validate_and_partition_orders(config)
    if result.reconciliation.status.value == "PROVISIONAL" and config.require_complete:
        raise ReconciliationError(
            "启用了 require_complete，但仍有成本或运费缺失",
            code="INCOMPLETE_RESULT_BLOCKED",
        )
    return RunOutcome(result=result, reports=publish_reports(result, config))


def _manifest_for_result(
    result: ValidationResult,
    config: RunConfig,
    *,
    pending_supplement_rows: int = 0,
) -> dict:
    manifest = build_manifest(
        config=config,
        status=result.reconciliation.status,
        inputs={role: table.metadata for role, table in result.tables.items()},
        issues=[
            issue for table in result.tables.values() for issue in table.issues
        ] + list(result.analysis.issues),
        completed_at=datetime.now(UTC),
    )
    manifest["stage"] = "P1-P11_REPORTS"
    manifest["order_partitions"] = result.partitions.counts()
    manifest["summary"] = serialize_summary(result.analysis.summary)
    manifest["reconciliation"] = serialize_reconciliation(result.reconciliation.checks)
    manifest["sabc"] = {
        "s_profit_share": str(config.s_profit_share),
        "a_profit_share": str(config.a_profit_share),
        "config_path": str(config.sabc_config.resolve()) if config.sabc_config else None,
    }
    manifest["pending_supplements"] = {
        "file": "待补成本运费.xlsx" if pending_supplement_rows else None,
        "rows": pending_supplement_rows,
    }
    return manifest


def publish_reports(result: ValidationResult, config: RunConfig) -> PublishedReports:
    """在同一文件系统内原子发布本次报告目录。"""

    parent = config.output_dir.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    destination = config.output_dir.resolve()
    temporary = parent / f".{destination.name}.tmp-{uuid4().hex}"
    backup = parent / f".{destination.name}.backup-{uuid4().hex}"
    try:
        temporary.mkdir(parents=False)
        excel = temporary / "订单成本利润分析.xlsx"
        html = temporary / "店铺经营复盘.html"
        manifest_path = temporary / "manifest.json"
        pending_path = temporary / "待补成本运费.xlsx"
        write_excel(result, config, excel)
        pending_rows = (
            write_pending_supplements(
                result,
                pending_path,
                supplements=result.tables.get("supplements"),
            )
            if result.reconciliation.status.value == "PROVISIONAL"
            else 0
        )
        write_html(result, config, html)
        write_manifest(
            _manifest_for_result(
                result,
                config,
                pending_supplement_rows=pending_rows,
            ),
            manifest_path,
        )
        required_files = [excel, html, manifest_path]
        if pending_rows:
            required_files.append(pending_path)
        if not all(file.exists() for file in required_files):
            raise OutputError("报告文件未全部生成", code="OUTPUT_FILES_MISSING")
        json.loads(manifest_path.read_text(encoding="utf-8"))

        if destination.exists():
            destination.replace(backup)
        temporary.replace(destination)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception as exc:
        if destination.exists() and backup.exists():
            shutil.rmtree(destination, ignore_errors=True)
            backup.replace(destination)
        elif backup.exists() and not destination.exists():
            backup.replace(destination)
        shutil.rmtree(temporary, ignore_errors=True)
        if isinstance(exc, OutputError):
            raise
        raise OutputError(f"正式报告发布失败：{exc}", code="OUTPUT_PUBLISH_FAILED") from exc
    return PublishedReports(
        excel=destination / excel.name,
        html=destination / html.name,
        manifest=destination / manifest_path.name,
        pending_supplements=(
            destination / pending_path.name if pending_rows else None
        ),
    )
