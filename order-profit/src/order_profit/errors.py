"""可定位的输入、核算与交付异常。"""

from __future__ import annotations

from collections.abc import Sequence

from order_profit.models import Issue, Severity


class OrderProfitError(Exception):
    """所有预期业务错误的基类。"""

    exit_code = 1

    def __init__(
        self,
        message: str,
        *,
        code: str = "ORDER_PROFIT_ERROR",
        issues: Sequence[Issue] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.issues = tuple(issues or ())

    def as_issue(self) -> Issue:
        return Issue(code=self.code, severity=Severity.ERROR, message=self.message)


class ConfigurationError(OrderProfitError):
    """运行参数或业务策略非法。"""

    exit_code = 2


class InputContractError(OrderProfitError):
    """输入文件、工作表、字段或值不符合契约。"""

    exit_code = 3


class NormalizationError(InputContractError):
    """标识符、日期或数值无法按严格规则标准化。"""


class ReconciliationError(OrderProfitError):
    """强制勾稽失败。"""

    exit_code = 4


class OutputError(OrderProfitError):
    """报告写入、读回或重算失败。"""

    exit_code = 5


class PipelineNotImplementedError(OrderProfitError):
    """完整核算流水线尚未开放，防止误交付。"""

    exit_code = 10
