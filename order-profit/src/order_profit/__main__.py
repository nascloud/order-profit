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
from order_profit.models import RunStatus
from order_profit.pipeline import validate_inputs
from order_profit.runtime import build_manifest, configure_logging, write_manifest


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

    validate_parser = subparsers.add_parser("validate-inputs", help="执行 P1～P3 输入契约和安全标准化")
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
    loaded = validate_inputs(config)
    metadata = {role: table.metadata for role, table in loaded.items()}
    issues = [issue for table in loaded.values() for issue in table.issues]
    for role, table in loaded.items():
        logger.info("%s：%s 行，SHA-256 %s…", role, len(table.data), table.metadata.sha256[:12])
    for issue in issues:
        logger.warning("%s：%s", issue.code, issue.message)
    manifest = build_manifest(
        config=config,
        status=RunStatus.PROVISIONAL,
        inputs=metadata,
        issues=issues,
        started_at=started_at,
    )
    manifest["stage"] = "P1-P3_INPUT_VALIDATION"
    manifest["note"] = "输入契约与安全标准化通过；尚未执行 P4 之后的利润核算。"
    path = config.output_dir / "validation-manifest.json"
    write_manifest(manifest, path)
    logger.info("P1～P3 校验通过；清单已写入 %s", path.resolve())
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
        raise PipelineNotImplementedError(
            "完整利润流水线将在 P4～P13 完成后开放；当前请使用 validate-inputs",
            code="PIPELINE_NOT_READY",
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
