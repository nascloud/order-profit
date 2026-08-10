"""强制勾稽关系与交付状态判定。"""

from __future__ import annotations

from dataclasses import dataclass

from order_profit.aggregate import AnalysisResult
from order_profit.errors import ReconciliationError
from order_profit.models import RunStatus
from order_profit.rules import OrderPartitions


@dataclass(frozen=True, slots=True)
class ReconciliationCheck:
    name: str
    expected: int
    actual: int

    @property
    def passed(self) -> bool:
        return self.expected == self.actual


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    status: RunStatus
    checks: tuple[ReconciliationCheck, ...]


def _sum_column(frame, column: str) -> int:
    return int(frame[column].sum()) if not frame.empty else 0


def validate_reconciliation(
    analysis: AnalysisResult,
    partitions: OrderPartitions,
    *,
    source_order_rows: int,
) -> ReconciliationResult:
    summary = analysis.summary
    links = analysis.links
    profit = analysis.profit
    promotion = analysis.promotion
    normal_complete = profit.normal[profit.normal["核算状态"] == "已核算"]
    closed_complete = profit.closed_shipped[
        profit.closed_shipped["核算状态"] == "已核算"
    ]
    checks = (
        ReconciliationCheck(
            "链接全部销售额",
            int(summary["全部有编码销售额_分"]),
            _sum_column(links, "全部销售额_分"),
        ),
        ReconciliationCheck(
            "链接已核算销售额",
            int(summary["已核算销售额_分"]),
            _sum_column(links, "已核算销售额_分"),
        ),
        ReconciliationCheck(
            "链接已核算退款",
            _sum_column(normal_complete, "有效退款_分"),
            _sum_column(links, "已核算有效退款_分"),
        ),
        ReconciliationCheck(
            "链接正常订单成本",
            _sum_column(normal_complete, "核算成本_分"),
            _sum_column(links, "正常订单货品成本_分"),
        ),
        ReconciliationCheck(
            "链接正常订单运费",
            _sum_column(normal_complete, "核算运费_分"),
            _sum_column(links, "正常订单运费_分"),
        ),
        ReconciliationCheck(
            "链接平台扣点",
            _sum_column(normal_complete, "平台扣点_分"),
            _sum_column(links, "平台扣点_分"),
        ),
        ReconciliationCheck(
            "链接综合税赋",
            _sum_column(normal_complete, "综合税赋_分"),
            _sum_column(links, "综合税赋_分"),
        ),
        ReconciliationCheck(
            "链接关闭损失",
            _sum_column(closed_complete, "关闭已发货损失_分"),
            _sum_column(links, "关闭已发货损失_分"),
        ),
        ReconciliationCheck(
            "链接推广花费",
            _sum_column(promotion.detail, "花费_分"),
            _sum_column(links, "推广花费_分"),
        ),
        ReconciliationCheck(
            "链接含推广利润",
            int(summary["含推广净利润_分"]),
            _sum_column(links, "含推广利润_分"),
        ),
        ReconciliationCheck(
            "订单源行守恒",
            source_order_rows,
            partitions.source_rows,
        ),
        ReconciliationCheck(
            "推广每日花费",
            _sum_column(promotion.detail, "花费_分"),
            _sum_column(promotion.daily, "推广花费_分"),
        ),
        ReconciliationCheck(
            "推广主体花费",
            _sum_column(promotion.detail, "花费_分"),
            _sum_column(promotion.products, "推广花费_分"),
        ),
    )
    failed = [check for check in checks if not check.passed]
    if failed:
        details = "；".join(
            f"{check.name}: expected={check.expected}, actual={check.actual}" for check in failed
        )
        raise ReconciliationError(
            f"强制勾稽失败：{details}",
            code="RECONCILIATION_FAILED",
        )
    status = (
        RunStatus.PROVISIONAL
        if int(summary["成本运费缺失行数"]) > 0
        else RunStatus.FINAL
    )
    return ReconciliationResult(status=status, checks=checks)
