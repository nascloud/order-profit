"""标识符、日期、数量和金额的严格标准化。"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from numbers import Integral, Real
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from order_profit.errors import NormalizationError
from order_profit.models import Issue, Severity, SourceLocation

CENT = Decimal("0.01")
MAX_SAFE_FLOAT_INTEGER = 9_007_199_254_740_991
MAX_EXCEL_NUMERIC_ID = 9_999_999_999_999_999
SCIENTIFIC_ID_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)[eE][+-]?\d+$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?$"
)


def is_missing(value: Any) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    try:
        return bool(missing)
    except (TypeError, ValueError):
        return False


def _normalization_error(
    *,
    code: str,
    message: str,
    value: Any,
    location: SourceLocation | None,
    suggestion: str | None = None,
) -> NormalizationError:
    issue = Issue(
        code=code,
        severity=Severity.ERROR,
        message=message,
        location=location or SourceLocation(),
        raw_value=value,
        suggestion=suggestion,
    )
    return NormalizationError(message, code=code, issues=[issue])


def normalize_id(value: Any, *, location: SourceLocation | None = None) -> str:
    """标准化订单号、商品 ID 或运单号，不改写字符串形式的 `.0`。"""

    if is_missing(value):
        return ""
    if isinstance(value, bool):
        raise _normalization_error(
            code="ID_BOOLEAN_INVALID",
            message="ID 不能是布尔值",
            value=value,
            location=location,
        )
    if isinstance(value, str):
        normalized = value.strip()
        if SCIENTIFIC_ID_PATTERN.fullmatch(normalized):
            raise _normalization_error(
                code="ID_SCIENTIFIC_NOTATION",
                message="ID 不能使用科学计数法",
                value=value,
                location=location,
                suggestion="请在源文件中将 ID 列设置为文本后重新导出",
            )
        return normalized
    if isinstance(value, Integral):
        if abs(value) > MAX_EXCEL_NUMERIC_ID:
            raise _normalization_error(
                code="ID_NUMERIC_PRECISION_RISK",
                message="数值型 ID 超过 Excel 可可靠保存的 16 位范围",
                value=value,
                location=location,
                suggestion="请从源系统重新导出为文本格式，程序不能恢复丢失数字",
            )
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise _normalization_error(
                code="ID_NUMERIC_NOT_INTEGER",
                message="数值型 ID 必须是有限整数",
                value=value,
                location=location,
            )
        integer = int(value)
        if abs(integer) > MAX_EXCEL_NUMERIC_ID:
            raise _normalization_error(
                code="ID_NUMERIC_PRECISION_RISK",
                message="数值型 ID 超过 Excel 可可靠保存的 16 位范围",
                value=value,
                location=location,
                suggestion="请从源系统重新导出为文本格式，程序不能恢复丢失数字",
            )
        return str(integer)
    if isinstance(value, Real):
        if not math.isfinite(value) or not value.is_integer():
            raise _normalization_error(
                code="ID_NUMERIC_NOT_INTEGER",
                message="数值型 ID 必须是有限整数",
                value=value,
                location=location,
            )
        if abs(value) > MAX_SAFE_FLOAT_INTEGER:
            raise _normalization_error(
                code="ID_FLOAT_PRECISION_RISK",
                message="数值型 ID 超过可安全表示范围，可能已被 Excel 舍入",
                value=value,
                location=location,
                suggestion="请从源系统重新导出为文本格式，程序不能恢复丢失数字",
            )
        return str(int(value))
    return str(value).strip()


def normalize_merchant_code(value: Any) -> str:
    """商家编码只转字符串并去首尾空格，不移除 `.0`。"""

    return "" if is_missing(value) else str(value).strip()


def money_to_cents(
    value: Any,
    *,
    allow_missing: bool = False,
    nonnegative: bool = False,
    location: SourceLocation | None = None,
) -> int | None:
    """使用 Decimal/ROUND_HALF_UP 将金额转换为整数分。"""

    if is_missing(value):
        if allow_missing:
            return None
        raise _normalization_error(
            code="MONEY_REQUIRED",
            message="金额不能为空",
            value=value,
            location=location,
        )
    if isinstance(value, bool):
        raise _normalization_error(
            code="MONEY_BOOLEAN_INVALID",
            message="金额不能是布尔值",
            value=value,
            location=location,
        )
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise _normalization_error(
            code="MONEY_INVALID",
            message="金额不是有效数值",
            value=value,
            location=location,
        ) from exc
    if not amount.is_finite():
        raise _normalization_error(
            code="MONEY_NOT_FINITE",
            message="金额必须是有限数值",
            value=value,
            location=location,
        )
    quantized = amount.quantize(CENT, rounding=ROUND_HALF_UP)
    if nonnegative and quantized < 0:
        raise _normalization_error(
            code="MONEY_NEGATIVE",
            message="该金额字段不能为负数",
            value=value,
            location=location,
        )
    return int(quantized * 100)


def normalize_count(
    value: Any,
    *,
    allow_missing: bool = False,
    location: SourceLocation | None = None,
) -> int | None:
    """将展现、点击等计数转换为非负整数。"""

    if is_missing(value):
        if allow_missing:
            return None
        raise _normalization_error(
            code="COUNT_REQUIRED",
            message="计数不能为空",
            value=value,
            location=location,
        )
    if isinstance(value, bool):
        raise _normalization_error(
            code="COUNT_BOOLEAN_INVALID",
            message="计数不能是布尔值",
            value=value,
            location=location,
        )
    try:
        count = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise _normalization_error(
            code="COUNT_INVALID",
            message="计数不是有效数值",
            value=value,
            location=location,
        ) from exc
    if not count.is_finite() or count != count.to_integral_value():
        raise _normalization_error(
            code="COUNT_NOT_INTEGER",
            message="计数必须是整数",
            value=value,
            location=location,
        )
    integer = int(count)
    if integer < 0:
        raise _normalization_error(
            code="COUNT_NEGATIVE",
            message="计数不能为负数",
            value=value,
            location=location,
        )
    return integer


def normalize_quantity(
    value: Any,
    *,
    allow_missing: bool = False,
    location: SourceLocation | None = None,
) -> int | None:
    """将购买数量转换为大于零的整数。"""

    if is_missing(value):
        if allow_missing:
            return None
        raise _normalization_error(
            code="QUANTITY_REQUIRED",
            message="购买数量不能为空",
            value=value,
            location=location,
        )
    if isinstance(value, bool):
        raise _normalization_error(
            code="QUANTITY_BOOLEAN_INVALID",
            message="购买数量不能是布尔值",
            value=value,
            location=location,
        )
    try:
        quantity = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise _normalization_error(
            code="QUANTITY_INVALID",
            message="购买数量不是有效数值",
            value=value,
            location=location,
        ) from exc
    if not quantity.is_finite() or quantity != quantity.to_integral_value():
        raise _normalization_error(
            code="QUANTITY_NOT_INTEGER",
            message="购买数量必须是整数",
            value=value,
            location=location,
        )
    integer = int(quantity)
    if integer <= 0:
        raise _normalization_error(
            code="QUANTITY_NOT_POSITIVE",
            message="购买数量必须大于 0",
            value=value,
            location=location,
        )
    return integer


def normalize_datetime(
    value: Any,
    *,
    timezone: str = "Asia/Shanghai",
    allow_missing: bool = False,
    location: SourceLocation | None = None,
) -> datetime | None:
    """严格解析规范允许的日期时间并统一到配置时区。"""

    if is_missing(value):
        if allow_missing:
            return None
        raise _normalization_error(
            code="DATETIME_REQUIRED",
            message="日期时间不能为空",
            value=value,
            location=location,
        )

    parsed: datetime
    if isinstance(value, pd.Timestamp):
        parsed = value.to_pydatetime()
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        text = value.strip()
        if DATE_PATTERN.fullmatch(text):
            try:
                parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
            except ValueError as exc:
                raise _normalization_error(
                    code="DATETIME_INVALID",
                    message="日期时间值非法",
                    value=value,
                    location=location,
                ) from exc
        elif DATETIME_PATTERN.fullmatch(text):
            iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
            try:
                parsed = datetime.fromisoformat(iso_text)
            except ValueError as exc:
                raise _normalization_error(
                    code="DATETIME_INVALID",
                    message="日期时间值非法",
                    value=value,
                    location=location,
                ) from exc
        else:
            raise _normalization_error(
                code="DATETIME_FORMAT_INVALID",
                message="日期时间格式不符合严格 ISO 契约",
                value=value,
                location=location,
                suggestion="请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS[.ffffff][时区偏移]",
            )
    else:
        raise _normalization_error(
            code="DATETIME_TYPE_INVALID",
            message="日期时间必须是 Excel 原生日期或规范允许的 ISO 文本",
            value=value,
            location=location,
        )

    target = ZoneInfo(timezone)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=target)
    return parsed.astimezone(target)


def add_source_audit_columns(
    data: pd.DataFrame,
    *,
    path: Path,
    sheet: str | None,
    file_sha256: str,
) -> pd.DataFrame:
    """返回带稳定源行审计字段的新 DataFrame。"""

    result = data.copy()
    short_hash = file_sha256[:16]
    source_rows = [int(index) + 2 for index in result.index]
    result.insert(0, "source_row_number", source_rows)
    result.insert(0, "source_sheet", sheet or "")
    result.insert(0, "source_file_id", short_hash)
    result.insert(
        3,
        "source_row_id",
        [f"{short_hash}:{sheet or ''}:{row}" for row in result["source_row_number"]],
    )
    result.attrs["source_path"] = str(path.resolve())
    return result


def normalize_ids(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """标准化指定 ID 列并返回副本。"""

    result = data.copy()
    for column in columns:
        if column not in result.columns:
            raise NormalizationError(
                f"无法标准化不存在的字段：{column}",
                code="NORMALIZE_COLUMN_MISSING",
            )
        result[column] = [
            normalize_id(
                value,
                location=SourceLocation(
                    file=result.attrs.get("source_path"),
                    sheet=(result.at[index, "source_sheet"] if "source_sheet" in result else None),
                    row=(int(result.at[index, "source_row_number"]) if "source_row_number" in result else None),
                    field=column,
                ),
            )
            for index, value in result[column].items()
        ]
    return result
