"""运行配置、业务策略与参数校验。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from order_profit.errors import ConfigurationError


class Platform(StrEnum):
    """受支持的店铺平台及其扣点配置键。"""

    TMALL = "tmall"
    TAOBAO = "taobao"


class RecalculationMode(StrEnum):
    """Excel 辅助公式重算方式。"""

    DISABLED = "disabled"
    AUTO = "auto"
    EXCEL = "excel"
    LIBREOFFICE = "libreoffice"


PLATFORM_FEE_RATES: dict[Platform, Decimal] = {
    Platform.TMALL: Decimal("0.06"),
    Platform.TAOBAO: Decimal("0.006"),
}
TAX_RATE = Decimal("0.023")
SPEC_VERSION = "1.1"


@dataclass(frozen=True, slots=True)
class RunConfig:
    """一次核算运行的完整、可审计配置。"""

    orders: Path
    start_date: date
    end_date: date
    platform: Platform
    output_dir: Path
    costs: Path | None = None
    freight: Path | None = None
    after_sales: Path | None = None
    promotion: Path | None = None
    supplements: Path | None = None
    orders_sheet: str = "export"
    costs_sheet: str = "Sheet1"
    freight_sheet: str | None = None
    after_sales_sheet: str | None = None
    supplements_sheet: str | None = None
    timezone: str = "Asia/Shanghai"
    overwrite_existing: bool = False
    require_complete: bool = False
    recalculation: RecalculationMode = RecalculationMode.DISABLED

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise ConfigurationError(
                "开始日期不能晚于结束日期",
                code="CONFIG_DATE_RANGE_INVALID",
            )
        if not self.orders_sheet.strip():
            raise ConfigurationError("订单工作表名称不能为空", code="CONFIG_SHEET_EMPTY")
        if not self.costs_sheet.strip():
            raise ConfigurationError("成本工作表名称不能为空", code="CONFIG_SHEET_EMPTY")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError(
                f"未知时区：{self.timezone}",
                code="CONFIG_TIMEZONE_INVALID",
            ) from exc

    @property
    def platform_fee_rate(self) -> Decimal:
        return PLATFORM_FEE_RATES[self.platform]

    @property
    def tax_rate(self) -> Decimal:
        return TAX_RATE

    def period_bounds(self) -> tuple[datetime, datetime]:
        """返回配置时区中的半开核算区间。"""

        timezone = ZoneInfo(self.timezone)
        start = datetime.combine(self.start_date, time.min, tzinfo=timezone)
        end_exclusive = datetime.combine(
            self.end_date + timedelta(days=1), time.min, tzinfo=timezone
        )
        return start, end_exclusive

    def input_paths(self) -> dict[str, Path]:
        """返回本次启用的输入文件。"""

        values = {
            "orders": self.orders,
            "costs": self.costs,
            "freight": self.freight,
            "after_sales": self.after_sales,
            "promotion": self.promotion,
            "supplements": self.supplements,
        }
        return {name: path for name, path in values.items() if path is not None}

    def to_dict(self) -> dict[str, Any]:
        """转换为可稳定写入 JSON 的配置快照。"""

        result = asdict(self)
        for key, value in tuple(result.items()):
            if isinstance(value, Path):
                result[key] = str(value.resolve())
            elif isinstance(value, date):
                result[key] = value.isoformat()
            elif isinstance(value, StrEnum):
                result[key] = value.value
        result["platform_fee_rate"] = str(self.platform_fee_rate)
        result["tax_rate"] = str(self.tax_rate)
        result["spec_version"] = SPEC_VERSION
        return result
