"""Excel、CSV 输入适配与字段契约校验。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd

from order_profit.errors import InputContractError
from order_profit.models import InputFileMetadata, Issue, Severity, SourceLocation
from order_profit.runtime import sha256_file

ORDER_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "主订单编号",
        "商品ID",
        "商品标题",
        "商品属性",
        "购买数量",
        "订单状态",
        "商家编码",
        "买家应付货款",
        "退款状态",
        "退款金额",
        "订单付款时间",
        "商家备注",
        "物流单号",
    }
)
COST_COLUMNS: Final[frozenset[str]] = frozenset({"编码", "成本", "运费"})
COST_COLUMN_ALIASES: Final[dict[str, str]] = {
    "商家编码": "编码",
    "单件成本": "成本",
    "单件运费": "运费",
}
FREIGHT_COLUMNS: Final[frozenset[str]] = frozenset({"运单号", "订单编码", "总运费"})
AFTER_SALES_COLUMNS: Final[frozenset[str]] = frozenset(
    {"订单编号", "退款编号", "退款状态", "退款总额", "退款完结时间"}
)
PROMOTION_COLUMNS: Final[frozenset[str]] = frozenset(
    {"日期", "主体ID", "主体名称", "展现量", "点击量", "花费", "总成交金额", "总成交笔数"}
)
SUPPLEMENT_COLUMNS: Final[frozenset[str]] = frozenset(
    {"主订单编号", "商品ID", "商家编码", "货品成本", "运费", "补充状态"}
)
SUPPLEMENT_OPTIONAL_COLUMNS: Final[frozenset[str]] = frozenset(
    {"明细序号", "补充商家编码"}
)


@dataclass(frozen=True, slots=True)
class LoadedTable:
    data: pd.DataFrame
    metadata: InputFileMetadata
    issues: tuple[Issue, ...] = ()


def _validate_file(path: Path, *, extensions: frozenset[str], role: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise InputContractError(
            f"{role}不存在：{resolved}",
            code="INPUT_FILE_NOT_FOUND",
        )
    if not resolved.is_file():
        raise InputContractError(
            f"{role}不是文件：{resolved}",
            code="INPUT_NOT_A_FILE",
        )
    suffix = resolved.suffix.lower()
    if suffix not in extensions:
        expected = "、".join(sorted(extensions))
        raise InputContractError(
            f"{role}格式不支持：{suffix or '无扩展名'}；允许 {expected}",
            code="INPUT_EXTENSION_UNSUPPORTED",
        )
    return resolved


def _normalize_headers(data: pd.DataFrame, *, path: Path, sheet: str | None) -> pd.DataFrame:
    normalized: list[str] = []
    for column in data.columns:
        if column is None or (not isinstance(column, str) and pd.isna(column)):
            normalized.append("")
        else:
            normalized.append(str(column).strip())

    empty_positions = [index + 1 for index, column in enumerate(normalized) if not column]
    if empty_positions:
        raise InputContractError(
            f"存在空字段名，列位置：{empty_positions}",
            code="INPUT_HEADER_EMPTY",
            issues=[
                Issue(
                    code="INPUT_HEADER_EMPTY",
                    severity=Severity.ERROR,
                    message="字段名不能为空",
                    location=SourceLocation(file=str(path), sheet=sheet),
                    raw_value=empty_positions,
                )
            ],
        )

    duplicates = sorted({column for column in normalized if normalized.count(column) > 1})
    if duplicates:
        raise InputContractError(
            f"字段名去除首尾空格后重复：{'、'.join(duplicates)}",
            code="INPUT_HEADER_DUPLICATE",
        )

    result = data.copy()
    result.columns = normalized
    return result


def _normalize_cost_columns(data: pd.DataFrame) -> pd.DataFrame:
    """兼容成本表业务表头；标准列与别名并存时以标准列为准。"""

    result = data.copy()
    for alias, target in COST_COLUMN_ALIASES.items():
        if alias not in result.columns:
            continue
        if target not in result.columns:
            result = result.rename(columns={alias: target})
        else:
            result = result.drop(columns=[alias])
    return result


def _validate_columns(
    data: pd.DataFrame,
    *,
    required: frozenset[str],
    path: Path,
    sheet: str | None,
) -> None:
    missing = sorted(required.difference(data.columns))
    if missing:
        raise InputContractError(
            f"缺少必需字段：{'、'.join(missing)}",
            code="INPUT_REQUIRED_COLUMNS_MISSING",
            issues=[
                Issue(
                    code="INPUT_REQUIRED_COLUMNS_MISSING",
                    severity=Severity.ERROR,
                    message="输入表缺少必需字段",
                    location=SourceLocation(file=str(path), sheet=sheet),
                    raw_value=missing,
                    suggestion="请使用规范模板导出或补齐字段后重试",
                )
            ],
        )


def _read_excel(
    path: Path,
    *,
    role: str,
    sheet: str | None,
    required: frozenset[str],
    extensions: frozenset[str] = frozenset({".xlsx"}),
) -> LoadedTable:
    resolved = _validate_file(path, extensions=extensions, role=role)
    try:
        book = pd.ExcelFile(resolved)
    except Exception as exc:
        raise InputContractError(
            f"无法打开{role}：{resolved.name}；{exc}",
            code="INPUT_EXCEL_OPEN_FAILED",
        ) from exc

    selected_sheet = sheet if sheet is not None else book.sheet_names[0]
    if selected_sheet not in book.sheet_names:
        available = "、".join(book.sheet_names)
        raise InputContractError(
            f"{role}缺少工作表“{selected_sheet}”；可用工作表：{available}",
            code="INPUT_SHEET_NOT_FOUND",
        )
    try:
        data = book.parse(sheet_name=selected_sheet, dtype=object)
    except Exception as exc:
        raise InputContractError(
            f"读取{role}工作表“{selected_sheet}”失败：{exc}",
            code="INPUT_EXCEL_READ_FAILED",
        ) from exc

    data = _normalize_headers(data, path=resolved, sheet=selected_sheet)
    _validate_columns(data, required=required, path=resolved, sheet=selected_sheet)
    empty_rows = data.isna() | data.apply(lambda column: column.map(lambda value: isinstance(value, str) and not value.strip()))
    all_empty_mask = empty_rows.all(axis=1)
    skipped_rows = [int(index) + 2 for index in data.index[all_empty_mask]]
    issues: list[Issue] = []
    if skipped_rows:
        issues.append(
            Issue(
                code="INPUT_EMPTY_ROWS_SKIPPED",
                severity=Severity.WARNING,
                message=f"已忽略 {len(skipped_rows)} 条全空排版行",
                location=SourceLocation(file=str(resolved), sheet=selected_sheet),
                raw_value=skipped_rows[:20],
            )
        )
        data = data.loc[~all_empty_mask].copy()
    metadata = InputFileMetadata(
        role=role,
        path=resolved,
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        rows=len(data),
        sheet=selected_sheet,
    )
    return LoadedTable(data=data, metadata=metadata, issues=tuple(issues))


def _read_csv_with_fallback(
    path: Path,
    *,
    role: str,
    required: frozenset[str],
    encoding: str | None = None,
) -> LoadedTable:
    resolved = _validate_file(path, extensions=frozenset({".csv"}), role=role)
    encodings = (encoding,) if encoding else ("utf-8-sig", "gb18030")
    last_decode_error: UnicodeDecodeError | None = None
    data: pd.DataFrame | None = None
    selected_encoding: str | None = None
    for candidate in encodings:
        try:
            data = pd.read_csv(resolved, encoding=candidate, dtype=object)
            selected_encoding = candidate
            break
        except UnicodeDecodeError as exc:
            last_decode_error = exc
        except Exception as exc:
            raise InputContractError(
                f"解析{role}失败：{exc}",
                code="INPUT_CSV_PARSE_FAILED",
            ) from exc
    if data is None or selected_encoding is None:
        raise InputContractError(
            f"{role}无法使用以下编码解码：{'、'.join(encodings)}",
            code="INPUT_CSV_DECODE_FAILED",
        ) from last_decode_error

    data = _normalize_headers(data, path=resolved, sheet=None)
    _validate_columns(data, required=required, path=resolved, sheet=None)
    metadata = InputFileMetadata(
        role=role,
        path=resolved,
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        rows=len(data),
        encoding=selected_encoding,
    )
    return LoadedTable(data=data, metadata=metadata)


def load_orders(path: Path, sheet: str = "export") -> LoadedTable:
    return _read_excel(path, role="订单表", sheet=sheet, required=ORDER_COLUMNS)


def load_costs(path: Path, sheet: str = "Sheet1") -> LoadedTable:
    table = _read_excel(
        path,
        role="成本编码表",
        sheet=sheet,
        required=frozenset(),
    )
    data = _normalize_cost_columns(table.data)
    _validate_columns(
        data,
        required=COST_COLUMNS,
        path=table.metadata.path,
        sheet=table.metadata.sheet,
    )
    return LoadedTable(data=data, metadata=table.metadata, issues=table.issues)


def load_freight(path: Path, sheet: str | None = None) -> LoadedTable:
    return _read_excel(
        path,
        role="运费表",
        sheet=sheet,
        required=FREIGHT_COLUMNS,
        extensions=frozenset({".xls", ".xlsx"}),
    )


def load_after_sales(path: Path, sheet: str | None = None) -> LoadedTable:
    return _read_excel(path, role="售后表", sheet=sheet, required=AFTER_SALES_COLUMNS)


def load_promotion(path: Path, encoding: str | None = None) -> LoadedTable:
    return _read_csv_with_fallback(
        path,
        role="推广报表",
        required=PROMOTION_COLUMNS,
        encoding=encoding,
    )


def load_supplements(path: Path, sheet: str | None = None) -> LoadedTable:
    return _read_excel(path, role="人工补充表", sheet=sheet, required=SUPPLEMENT_COLUMNS)
