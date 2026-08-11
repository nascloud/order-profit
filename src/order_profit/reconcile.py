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
    daily = analysis.daily
    products = analysis.products
    positive_links = links[(links["成本运费缺失行数"] == 0) & (links["含推广经营贡献利润_分"] > 0)] if not links.empty else links
    sab_links = links[links["SABC等级"].map(str).str.endswith(("S", "A", "B"))] if not links.empty else links
    c_links = links[(links["成本运费缺失行数"] == 0) & (links["含推广经营贡献利润_分"] <= 0)] if not links.empty else links
    graded_c_links = links[links["SABC等级"].map(str).str.endswith("C")] if not links.empty else links
    checks = (
        ReconciliationCheck(
            "链接全部销售额",
            int(summary["已付款销售额_分"]),
            _sum_column(links, "销售额_分"),
        ),
        ReconciliationCheck(
            "链接已核算销售额",
            int(summary["已核算销售额_分"]),
            _sum_column(links, "已核算销售额_分"),
        ),
        ReconciliationCheck(
            "链接已核算退款",
            int(summary["已核算订单批次成功退款_分"]),
            _sum_column(links, "已核算订单批次成功退款_分"),
        ),
        ReconciliationCheck("链接订单批次退款", int(summary["订单批次成功退款金额_分"]), _sum_column(links, "订单批次成功退款_分")),
        ReconciliationCheck("链接购买数量", int(summary["购买数量"]), _sum_column(links, "购买数量")),
        ReconciliationCheck("链接推广归因成交", int(summary["推广归因成交金额_分"]), _sum_column(links, "推广归因成交金额_分")),
        ReconciliationCheck(
            "链接正常订单成本",
            int(summary["已核算货品成本_分"]),
            _sum_column(links, "货品成本_分"),
        ),
        ReconciliationCheck(
            "链接正常订单运费",
            int(summary["已核算运费_分"]),
            _sum_column(links, "运费_分"),
        ),
        ReconciliationCheck(
            "链接平台扣点",
            int(summary["已核算平台扣点_分"]),
            _sum_column(links, "平台扣点_分"),
        ),
        ReconciliationCheck(
            "链接综合税赋",
            int(summary["已核算综合税赋_分"]),
            _sum_column(links, "综合税赋_分"),
        ),
        ReconciliationCheck(
            "链接关闭损失",
            int(summary["关闭已发货损失_分"]),
            _sum_column(links, "关闭已发货损失_分"),
        ),
        ReconciliationCheck(
            "链接推广花费",
            _sum_column(promotion.detail, "花费_分"),
            _sum_column(links, "推广花费_分"),
        ),
        ReconciliationCheck(
            "链接含推广利润",
            int(summary["含推广经营贡献利润_分"]),
            _sum_column(links, "含推广经营贡献利润_分"),
        ),
        ReconciliationCheck("每日销售额", int(summary["已付款销售额_分"]), _sum_column(daily, "销售额_分")),
        ReconciliationCheck("每日主订单数", int(summary["已付款主订单数"]), _sum_column(daily, "已付款主订单数")),
        ReconciliationCheck("每日购买数量", int(summary["购买数量"]), _sum_column(daily, "购买数量")),
        ReconciliationCheck("每日订单批次退款", int(summary["订单批次成功退款金额_分"]), _sum_column(daily, "订单批次成功退款_分")),
        ReconciliationCheck("每日期间退款", int(summary["期间退款完结金额_分"]), _sum_column(daily, "期间退款完结金额_分")),
        ReconciliationCheck("每日货品成本", int(summary["已核算货品成本_分"]), _sum_column(daily, "货品成本_分")),
        ReconciliationCheck("每日运费", int(summary["已核算运费_分"]), _sum_column(daily, "运费_分")),
        ReconciliationCheck("每日平台扣点", int(summary["已核算平台扣点_分"]), _sum_column(daily, "平台扣点_分")),
        ReconciliationCheck("每日综合税赋", int(summary["已核算综合税赋_分"]), _sum_column(daily, "综合税赋_分")),
        ReconciliationCheck("每日关闭损失", int(summary["关闭已发货损失_分"]), _sum_column(daily, "关闭已发货损失_分")),
        ReconciliationCheck("每日推广花费", int(summary["推广花费_分"]), _sum_column(daily, "推广花费_分")),
        ReconciliationCheck("每日推广归因成交", int(summary["推广归因成交金额_分"]), _sum_column(daily, "推广归因成交金额_分")),
        ReconciliationCheck("每日经营贡献利润", int(summary["含推广经营贡献利润_分"]), _sum_column(daily, "含推广经营贡献利润_分")),
        ReconciliationCheck("产品销售额", int(summary["已付款销售额_分"]), _sum_column(products, "销售额_分")),
        ReconciliationCheck("产品净销售额", int(summary["净销售额_分"]), _sum_column(products, "净销售额_分")),
        ReconciliationCheck("产品已核算销售额", int(summary["已核算销售额_分"]), _sum_column(products, "已核算销售额_分")),
        ReconciliationCheck("产品购买数量", int(summary["购买数量"]), _sum_column(products, "购买数量")),
        ReconciliationCheck("产品订单批次退款", int(summary["订单批次成功退款金额_分"]), _sum_column(products, "订单批次成功退款_分")),
        ReconciliationCheck("产品货品成本", int(summary["已核算货品成本_分"]), _sum_column(products, "货品成本_分")),
        ReconciliationCheck("产品运费", int(summary["已核算运费_分"]), _sum_column(products, "运费_分")),
        ReconciliationCheck("产品平台扣点", int(summary["已核算平台扣点_分"]), _sum_column(products, "平台扣点_分")),
        ReconciliationCheck("产品综合税赋", int(summary["已核算综合税赋_分"]), _sum_column(products, "综合税赋_分")),
        ReconciliationCheck("产品关闭损失", int(summary["关闭已发货损失_分"]), _sum_column(products, "关闭已发货损失_分")),
        ReconciliationCheck("产品推广花费", int(summary["推广花费_分"]), _sum_column(products, "推广花费_分")),
        ReconciliationCheck("产品推广归因成交", int(summary["推广归因成交金额_分"]), _sum_column(products, "推广归因成交金额_分")),
        ReconciliationCheck("产品经营贡献利润", int(summary["含推广经营贡献利润_分"]), _sum_column(products, "含推广经营贡献利润_分")),
        ReconciliationCheck(
            "SAB 正利润守恒",
            _sum_column(positive_links, "含推广经营贡献利润_分"),
            _sum_column(sab_links, "含推广经营贡献利润_分"),
        ),
        ReconciliationCheck(
            "C 类链接数量",
            len(c_links),
            len(graded_c_links),
        ),
        ReconciliationCheck("盈利链接数量", int(summary["盈利链接数"]), int((positive_links["含推广经营贡献利润_分"] > 0).sum()) if not positive_links.empty else 0),
        ReconciliationCheck("亏损链接数量", int(summary["亏损链接数"]), len(c_links)),
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
    has_incomplete_data = (
        int(summary["成本运费缺失行数"]) > 0
        or len(partitions.missing_merchant_code) > 0
        or len(partitions.payment_anomaly) > 0
    )
    status = RunStatus.PROVISIONAL if has_incomplete_data else RunStatus.FINAL
    return ReconciliationResult(status=status, checks=checks)
