"""命令行入口。"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from order_profit import __version__
from order_profit.config import Platform, RecalculationMode, RunConfig
from order_profit.errors import OrderProfitError, PipelineNotImplementedError
from order_profit.pipeline import validate_and_partition_orders
from order_profit.reporting import execute_run
from order_profit.runtime import (
    build_manifest,
    configure_logging,
    deduplicate_issues,
    serialize_reconciliation,
    serialize_summary,
    write_manifest,
)


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须使用 YYYY-MM-DD 格式") from exc


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--orders", type=Path, required=True, help="订单 .xlsx 文件")
    parser.add_argument("--costs", type=Path, help="成本编码表 .xlsx 文件")
    parser.add_argument("--freight", type=Path, help="运费 .xls/.xlsx 文件")
    parser.add_argument("--after-sales", type=Path, help="售后 .xlsx 文件")
    parser.add_argument("--promotion", type=Path, help="推广 .csv 文件")
    parser.add_argument("--supplements", type=Path, help="人工补充 .xlsx 文件")
    parser.add_argument("--start-date", type=_parse_date, required=True, help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", type=_parse_date, required=True, help="结束日期 YYYY-MM-DD")
    parser.add_argument("--platform", choices=tuple(Platform), type=Platform, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--orders-sheet", default="export")
    parser.add_argument("--costs-sheet", default="Sheet1")
    parser.add_argument("--freight-sheet")
    parser.add_argument("--after-sales-sheet")
    parser.add_argument("--supplements-sheet")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--overwrite-existing", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument(
        "--recalculation",
        choices=tuple(RecalculationMode),
        type=RecalculationMode,
        default=RecalculationMode.DISABLED,
    )
    parser.add_argument("--verbose", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="订单利润核算与报表程序")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser("validate-inputs", help="执行 P1～P4 输入契约、标准化与订单分区")
    _add_common_arguments(validate_parser)

    run_parser = subparsers.add_parser("run", help="执行完整核算（P4 以后完成前拒绝运行）")
    _add_common_arguments(run_parser)
    return parser


def _config_from_args(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        orders=args.orders,
        costs=args.costs,
        freight=args.freight,
        after_sales=args.after_sales,
        promotion=args.promotion,
        supplements=args.supplements,
        start_date=args.start_date,
        end_date=args.end_date,
        platform=args.platform,
        output_dir=args.output_dir,
        orders_sheet=args.orders_sheet,
        costs_sheet=args.costs_sheet,
        freight_sheet=args.freight_sheet,
        after_sales_sheet=args.after_sales_sheet,
        supplements_sheet=args.supplements_sheet,
        timezone=args.timezone,
        overwrite_existing=args.overwrite_existing,
        require_complete=args.require_complete,
        recalculation=args.recalculation,
    )


def _validate_command(config: RunConfig, *, verbose: bool) -> int:
    logger = configure_logging(verbose=verbose)
    started_at = datetime.now().astimezone()
    validation = validate_and_partition_orders(config)
    loaded = validation.tables
    partitions = validation.partitions
    cost_result = validation.costs
    analysis = validation.analysis
    reconciliation = validation.reconciliation
    metadata = {role: table.metadata for role, table in loaded.items()}
    issues = [issue for table in loaded.values() for issue in table.issues]
    issues.extend(analysis.issues)
    issues = deduplicate_issues(issues)
    for role, table in loaded.items():
        logger.info("%s：%s 行，SHA-256 %s…", role, len(table.data), table.metadata.sha256[:12])
    counts = partitions.counts()
    logger.info(
        "订单分区：删除 %s，超期 %s，正常 %s，关闭已发货 %s，无编码 %s，其他状态 %s",
        counts["DELETED_BY_RULE"],
        counts["OUT_OF_PERIOD"],
        counts["NORMAL_CODED"],
        counts["CLOSED_SHIPPED_CODED"],
        counts["MISSING_MERCHANT_CODE"],
        counts["OTHER_STATUS"],
    )
    logger.info(
        "成本运费：成本缺失 %s 行，运费缺失 %s 行，补充审计 %s 行",
        cost_result.missing_cost_rows,
        cost_result.missing_freight_rows,
        len(cost_result.supplement_audit),
    )
    logger.info(
        "核算摘要：状态 %s，已核算销售额 %.2f 元，含推广净利润 %.2f 元，有效链接 %s",
        reconciliation.status.value,
        int(analysis.summary["已核算销售额_分"]) / 100,
        int(analysis.summary["含推广净利润_分"]) / 100,
        analysis.summary["有效商品链接"],
    )
    for issue in issues:
        logger.warning("%s：%s", issue.code, issue.message)
    manifest = build_manifest(
        config=config,
        status=reconciliation.status,
        inputs=metadata,
        issues=issues,
        started_at=started_at,
    )
    manifest["stage"] = "P1-P9_IN_MEMORY_RECONCILIATION"
    manifest["order_partitions"] = counts
    manifest["cost_freight"] = {
        "missing_cost_rows": cost_result.missing_cost_rows,
        "missing_freight_rows": cost_result.missing_freight_rows,
        "supplement_audit_rows": len(cost_result.supplement_audit),
    }
    manifest["summary"] = serialize_summary(analysis.summary)
    manifest["reconciliation"] = serialize_reconciliation(reconciliation.checks)
    manifest["note"] = "内存核算与强制勾稽通过；尚未生成 P10～P13 Excel、HTML 和桌面交付物。"
    path = config.output_dir / "validation-manifest.json"
    write_manifest(manifest, path)
    logger.info("P1～P9 内存核算与勾稽通过；清单已写入 %s", path.resolve())
    if reconciliation.status.value == "PROVISIONAL" and config.require_complete:
        logger.error("启用了 --require-complete，但仍有成本或运费缺失")
        return 4
    return 0


def _run_command(config: RunConfig, *, verbose: bool) -> int:
    logger = configure_logging(verbose=verbose)
    outcome = execute_run(config)
    logger.info("报告状态：%s", outcome.result.reconciliation.status.value)
    logger.info("Excel：%s", outcome.reports.excel)
    logger.info("运营复盘 HTML：%s", outcome.reports.html)
    logger.info("运行清单：%s", outcome.reports.manifest)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        config = _config_from_args(args)
        if args.command == "validate-inputs":
            return _validate_command(config, verbose=args.verbose)
        if args.command == "run":
            return _run_command(config, verbose=args.verbose)
        raise PipelineNotImplementedError(
            "未知命令",
            code="PIPELINE_COMMAND_UNKNOWN",
        )
    except OrderProfitError as exc:
        print(f"错误 [{exc.code}]：{exc.message}", file=sys.stderr)
        for issue in exc.issues:
            location = issue.location
            parts = [part for part in (location.file, location.sheet, location.row, location.field) if part]
            suffix = f"（{' / '.join(map(str, parts))}）" if parts else ""
            print(f"  - {issue.code}: {issue.message}{suffix}", file=sys.stderr)
            if issue.suggestion:
                print(f"    处理建议：{issue.suggestion}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
