"""订单退款、平台费用、税赋、利润与售后复核。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd

from order_profit.config import RunConfig
from order_profit.costs import CostResolutionResult
from order_profit.inputs import LoadedTable
from order_profit.models import Issue, Severity, SourceLocation
from order_profit.normalize import is_missing


@dataclass(frozen=True, slots=True)
class ProfitResult:
    normal: pd.DataFrame
    closed_shipped: pd.DataFrame
    after_sales_reconciliation: pd.DataFrame
    issues: tuple[Issue, ...] = ()

    @property
    def incomplete_rows(self) -> int:
        return int((self.normal["核算状态"] != "已核算").sum()) + int(
            (self.closed_shipped["核算状态"] != "已核算").sum()
        )


def _rate_amount(base_cents: int, rate: Decimal) -> int:
    amount = (Decimal(base_cents) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(amount)


def calculate_order_profit(costs: CostResolutionResult, config: RunConfig) -> ProfitResult:
    normal = costs.normal.copy()
    effective_refunds: list[int] = []
    fee_bases: list[int] = []
    platform_fees: list[int] = []
    taxes: list[int] = []
    profits: list[int | None] = []
    margins: list[Decimal] = []
    statuses: list[str] = []
    zero_denominator: list[bool] = []
    issues = list(costs.issues)

    for _, row in normal.iterrows():
        receipt = int(row["买家应付货款_分"])
        refund = int(row["退款金额_分"]) if str(row["退款状态"]) == "退款成功" else 0
        base = max(receipt - refund, 0)
        platform_fee = _rate_amount(base, config.platform_fee_rate)
        tax = _rate_amount(base, config.tax_rate)
        cost = row.get("核算成本_分")
        freight = row.get("核算运费_分")
        complete = not is_missing(cost) and not is_missing(freight)
        if complete:
            profit = receipt - refund - int(cost) - int(freight) - platform_fee - tax
            margin = Decimal(profit) / Decimal(receipt) if receipt else Decimal("0")
            status = "已核算"
        else:
            profit = None
            margin = Decimal("0")
            status = "成本或运费缺失"
        effective_refunds.append(refund)
        fee_bases.append(base)
        platform_fees.append(platform_fee)
        taxes.append(tax)
        profits.append(profit)
        margins.append(margin)
        zero_denominator.append(receipt == 0)
        statuses.append(status)
        if refund > receipt:
            issues.append(
                Issue(
                    code="ORDER_REFUND_EXCEEDS_RECEIPT",
                    severity=Severity.WARNING,
                    message="有效退款大于实收金额，未自动截断",
                    location=SourceLocation(
                        sheet=str(row.get("source_sheet")),
                        row=int(row["source_row_number"]),
                        field="退款金额",
                    ),
                    raw_value={"receipt_cents": receipt, "refund_cents": refund},
                )
            )

    normal["实收金额_分"] = normal["买家应付货款_分"]
    normal["有效退款_分"] = effective_refunds
    normal["费用计费基数_分"] = fee_bases
    normal["平台扣点_分"] = platform_fees
    normal["综合税赋_分"] = taxes
    normal["正常订单利润_分"] = pd.Series(profits, index=normal.index, dtype=object)
    normal["利润率"] = margins
    normal["零分母"] = zero_denominator
    normal["核算状态"] = statuses

    closed = costs.closed_shipped.copy()
    losses: list[int | None] = []
    closed_profits: list[int | None] = []
    closed_statuses: list[str] = []
    for _, row in closed.iterrows():
        cost = row.get("核算成本_分")
        freight = row.get("核算运费_分")
        if not is_missing(cost) and not is_missing(freight):
            loss = int(cost) + int(freight)
            status = "已核算"
        else:
            loss = None
            status = "成本或运费缺失"
        losses.append(loss)
        closed_profits.append(-loss if loss is not None else None)
        closed_statuses.append(status)
    closed["实收金额_分"] = 0
    closed["有效退款_分"] = 0
    closed["平台扣点_分"] = 0
    closed["综合税赋_分"] = 0
    closed["关闭已发货损失_分"] = pd.Series(losses, index=closed.index, dtype=object)
    closed["关闭明细利润_分"] = pd.Series(closed_profits, index=closed.index, dtype=object)
    closed["核算状态"] = closed_statuses

    return ProfitResult(
        normal=normal,
        closed_shipped=closed,
        after_sales_reconciliation=pd.DataFrame(),
        issues=tuple(issues),
    )


def reconcile_after_sales(
    profit: ProfitResult,
    after_sales: LoadedTable | None,
    config: RunConfig,
) -> ProfitResult:
    """按退款完结期间执行主订单级售后复核，不修改利润。"""

    if after_sales is None:
        return profit

    start, end_exclusive = config.period_bounds()
    sales = after_sales.data
    successful = sales[
        (sales["退款状态"].map(str) == "退款成功")
        & sales["退款完结时间_标准"].notna()
        & sales["退款完结时间_标准"].map(lambda value: start <= value < end_exclusive)
    ].copy()
    after_summary = (
        successful.groupby("订单编号", as_index=False)["退款总额_分"]
        .sum()
        .rename(columns={"订单编号": "主订单编号", "退款总额_分": "售后成功退款_分"})
    )
    order_summary = (
        profit.normal.groupby("主订单编号", as_index=False)["有效退款_分"]
        .sum()
        .rename(columns={"有效退款_分": "订单有效退款_分"})
    )
    reconciliation = after_summary.merge(order_summary, on="主订单编号", how="outer").fillna(0)
    reconciliation["售后成功退款_分"] = reconciliation["售后成功退款_分"].astype(int)
    reconciliation["订单有效退款_分"] = reconciliation["订单有效退款_分"].astype(int)
    reconciliation["退款差异_分"] = (
        reconciliation["售后成功退款_分"] - reconciliation["订单有效退款_分"]
    )
    reconciliation["复核状态"] = reconciliation["退款差异_分"].map(
        lambda value: "一致" if value == 0 else "不一致"
    )
    issues = list(profit.issues)
    for _, row in reconciliation[reconciliation["退款差异_分"] != 0].iterrows():
        issues.append(
            Issue(
                code="AFTER_SALES_REFUND_MISMATCH",
                severity=Severity.WARNING,
                message="售后表与订单表主订单级退款金额不一致",
                raw_value={
                    "主订单编号": row["主订单编号"],
                    "售后成功退款_分": int(row["售后成功退款_分"]),
                    "订单有效退款_分": int(row["订单有效退款_分"]),
                },
                suggestion="核对退款归属和期间；首版只复核，不追加利润",
            )
        )
    return ProfitResult(
        normal=profit.normal,
        closed_shipped=profit.closed_shipped,
        after_sales_reconciliation=reconciliation,
        issues=tuple(issues),
    )
