"""订单清洗、期间过滤与互斥分类规则。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import pandas as pd

from order_profit.config import RunConfig
from order_profit.errors import NormalizationError, ReconciliationError
from order_profit.inputs import LoadedTable
from order_profit.models import Issue, Severity, SourceLocation
from order_profit.normalize import is_missing, normalize_quantity

NORMAL_STATUSES: Final[frozenset[str]] = frozenset(
    {"交易成功", "卖家已发货，等待买家确认"}
)
CLOSED_STATUS: Final[str] = "交易关闭"
PRICE_DIFFERENCE_TITLE: Final[str] = "补差价专用"


def is_price_difference(row: pd.Series) -> bool:
    """仅按去除首尾空格后的商品标题精确识别虚拟补差价明细。"""

    return _text(row.get("商品标题")).strip() == PRICE_DIFFERENCE_TITLE


class CleaningReason(StrEnum):
    CLOSED_WITHOUT_LOGISTICS = "交易关闭且无物流单号"
    NOTE_CONTAINS_D = "商家备注包含字母D/d"
    NOTE_CONTAINS_S = "商家备注包含字母S/s"


class OrderPartition(StrEnum):
    DELETED_BY_RULE = "DELETED_BY_RULE"
    OUT_OF_PERIOD = "OUT_OF_PERIOD"
    NORMAL_CODED = "NORMAL_CODED"
    CLOSED_SHIPPED_CODED = "CLOSED_SHIPPED_CODED"
    MISSING_MERCHANT_CODE = "MISSING_MERCHANT_CODE"
    OTHER_STATUS = "OTHER_STATUS"


@dataclass(frozen=True, slots=True)
class OrderPartitions:
    """成功 P4 运行产生的六个互斥订单分区。"""

    deleted: pd.DataFrame
    out_of_period: pd.DataFrame
    normal: pd.DataFrame
    closed_shipped: pd.DataFrame
    missing_merchant_code: pd.DataFrame
    other_status: pd.DataFrame
    issues: tuple[Issue, ...] = ()

    def as_dict(self) -> dict[OrderPartition, pd.DataFrame]:
        return {
            OrderPartition.DELETED_BY_RULE: self.deleted,
            OrderPartition.OUT_OF_PERIOD: self.out_of_period,
            OrderPartition.NORMAL_CODED: self.normal,
            OrderPartition.CLOSED_SHIPPED_CODED: self.closed_shipped,
            OrderPartition.MISSING_MERCHANT_CODE: self.missing_merchant_code,
            OrderPartition.OTHER_STATUS: self.other_status,
        }

    def counts(self) -> dict[str, int]:
        return {partition.value: len(data) for partition, data in self.as_dict().items()}

    @property
    def source_rows(self) -> int:
        return sum(self.counts().values())


def _text(value: object) -> str:
    return "" if is_missing(value) else str(value)


def _location(row: pd.Series, field: str) -> SourceLocation:
    source_row = row.get("source_row_number")
    return SourceLocation(
        file=row.attrs.get("source_path"),
        sheet=_text(row.get("source_sheet")) or None,
        row=(int(source_row) if not is_missing(source_row) else None),
        field=field,
    )


def _cleaning_reasons(row: pd.Series) -> tuple[str, ...]:
    reasons: list[str] = []
    status = _text(row.get("订单状态"))
    logistics = _text(row.get("物流单号"))
    note = _text(row.get("商家备注"))
    note_casefolded = note.casefold()

    if status == CLOSED_STATUS and not logistics:
        reasons.append(CleaningReason.CLOSED_WITHOUT_LOGISTICS.value)
    if "d" in note_casefolded:
        reasons.append(CleaningReason.NOTE_CONTAINS_D.value)
    if "s" in note_casefolded:
        reasons.append(CleaningReason.NOTE_CONTAINS_S.value)
    return tuple(reasons)


def apply_cleaning_rules(table: LoadedTable) -> tuple[pd.DataFrame, pd.DataFrame]:
    """独立计算所有清洗原因，返回保留行和删除行。"""

    data = table.data.copy()
    data.attrs.update(table.data.attrs)
    data["cleaning_reasons"] = data.apply(_cleaning_reasons, axis=1)
    deleted_mask = data["cleaning_reasons"].map(bool)
    deleted = data.loc[deleted_mask].copy()
    retained = data.loc[~deleted_mask].copy()
    deleted["partition"] = OrderPartition.DELETED_BY_RULE.value
    return retained, deleted


def filter_period(
    data: pd.DataFrame,
    config: RunConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """对清洗保留行执行严格付款时间校验和半开区间过滤。"""

    start, end_exclusive = config.period_bounds()

    missing = data["订单付款时间_标准"].isna()
    if missing.any():
        first_index = data.index[missing][0]
        row = data.loc[first_index]
        issue = Issue(
            code="ORDER_PAYMENT_TIME_REQUIRED",
            severity=Severity.ERROR,
            message="未命中清洗删除规则的订单付款时间不能为空",
            location=_location(row, "订单付款时间"),
            raw_value=row.get("订单付款时间"),
            suggestion="请补齐付款时间或修正源订单后重试",
        )
        raise NormalizationError(issue.message, code=issue.code, issues=[issue])

    in_period = data["订单付款时间_标准"].map(
        lambda value: start <= value < end_exclusive
    )
    retained = data.loc[in_period].copy()
    out_of_period = data.loc[~in_period].copy()
    out_of_period["partition"] = OrderPartition.OUT_OF_PERIOD.value
    return retained, out_of_period


def _validate_accountable_order(row: pd.Series, *, normal: bool) -> int:
    """校验进入正常/关闭已发货核算的必需字段。"""

    if not _text(row.get("商品ID")):
        issue = Issue(
            code="ORDER_PRODUCT_ID_REQUIRED",
            severity=Severity.ERROR,
            message="可核算的有效正常/关闭已发货订单商品ID不能为空",
            location=_location(row, "商品ID"),
            raw_value=row.get("商品ID"),
            suggestion="请补齐商品ID后重试，程序不能猜测链接归属",
        )
        raise NormalizationError(issue.message, code=issue.code, issues=[issue])
    quantity = normalize_quantity(
        row.get("购买数量"),
        location=_location(row, "购买数量"),
    )
    if normal and is_missing(row.get("买家应付货款_分")):
        issue = Issue(
            code="ORDER_PAYMENT_REQUIRED",
            severity=Severity.ERROR,
            message="正常订单买家应付货款不能为空",
            location=_location(row, "买家应付货款"),
            raw_value=row.get("买家应付货款"),
            suggestion="请补齐当前商品明细行货款后重试",
        )
        raise NormalizationError(issue.message, code=issue.code, issues=[issue])
    if normal and _text(row.get("退款状态")) == "退款成功" and is_missing(
        row.get("退款金额_分")
    ):
        issue = Issue(
            code="ORDER_REFUND_AMOUNT_REQUIRED",
            severity=Severity.ERROR,
            message="退款成功的正常订单退款金额不能为空",
            location=_location(row, "退款金额"),
            raw_value=row.get("退款金额"),
            suggestion="请补齐退款金额后重试",
        )
        raise NormalizationError(issue.message, code=issue.code, issues=[issue])
    return quantity


def _has_direct_cost_and_freight(row: pd.Series) -> bool:
    """无编码明细在成本、运费均有明确金额时仍可核算。"""

    has_cost = not is_missing(row.get("补充货品成本_分")) or not is_missing(
        row.get("货品成本_分")
    )
    has_freight = not is_missing(row.get("补充运费_分")) or not is_missing(
        row.get("运费_分")
    )
    return has_cost and has_freight


def classify_orders(data: pd.DataFrame) -> tuple[dict[OrderPartition, pd.DataFrame], tuple[Issue, ...]]:
    """把期间内订单分为四个互斥业务分区。"""

    status = data["订单状态"].map(_text)
    merchant_code = data["商家编码"].map(_text)
    eligible_status = status.isin(NORMAL_STATUSES | {CLOSED_STATUS})
    price_difference_mask = data.apply(is_price_difference, axis=1)
    direct_amounts_mask = data.apply(_has_direct_cost_and_freight, axis=1)
    missing_code_mask = (
        eligible_status
        & merchant_code.eq("")
        & ~price_difference_mask
        & ~direct_amounts_mask
    )
    normal_mask = status.isin(NORMAL_STATUSES) & ~missing_code_mask
    closed_mask = status.eq(CLOSED_STATUS) & ~missing_code_mask
    other_mask = ~(missing_code_mask | normal_mask | closed_mask)

    partitions: dict[OrderPartition, pd.DataFrame] = {
        OrderPartition.NORMAL_CODED: data.loc[normal_mask].copy(),
        OrderPartition.CLOSED_SHIPPED_CODED: data.loc[closed_mask].copy(),
        OrderPartition.MISSING_MERCHANT_CODE: data.loc[missing_code_mask].copy(),
        OrderPartition.OTHER_STATUS: data.loc[other_mask].copy(),
    }
    issues: list[Issue] = []
    for partition, frame in partitions.items():
        frame["partition"] = partition.value

    for partition in (OrderPartition.NORMAL_CODED, OrderPartition.CLOSED_SHIPPED_CODED):
        frame = partitions[partition]
        if frame.empty:
            frame["购买数量_标准"] = pd.Series(index=frame.index, dtype=object)
            continue
        quantities = [
            _validate_accountable_order(row, normal=partition is OrderPartition.NORMAL_CODED)
            for _, row in frame.iterrows()
        ]
        frame["购买数量_标准"] = quantities
        frame["是否补差价专用"] = frame.apply(is_price_difference, axis=1)

    missing_frame = partitions[OrderPartition.MISSING_MERCHANT_CODE]
    for _, row in missing_frame.iterrows():
        issues.append(
            Issue(
                code="ORDER_MERCHANT_CODE_MISSING",
                severity=Severity.WARNING,
                message="有效状态订单缺少商家编码，不纳入利润",
                location=_location(row, "商家编码"),
                raw_value=row.get("商家编码"),
                suggestion="补齐商家编码后通过人工补充或重新运行核算",
            )
        )

    other_frame = partitions[OrderPartition.OTHER_STATUS]
    for _, row in other_frame.iterrows():
        issues.append(
            Issue(
                code="ORDER_STATUS_UNRECOGNIZED",
                severity=Severity.WARNING,
                message="订单状态不属于首版正常或关闭已发货口径",
                location=_location(row, "订单状态"),
                raw_value=row.get("订单状态"),
                suggestion="确认业务状态后再决定是否扩展分类规则",
            )
        )
    return partitions, tuple(issues)


def _assert_partition_conservation(source: pd.DataFrame, result: OrderPartitions) -> None:
    source_ids = source["source_row_id"].tolist()
    partition_ids = [
        source_id
        for frame in result.as_dict().values()
        for source_id in frame["source_row_id"].tolist()
    ]
    if len(partition_ids) != len(set(partition_ids)):
        raise ReconciliationError(
            "订单一级分区存在重复源行",
            code="ORDER_PARTITION_OVERLAP",
        )
    if set(source_ids) != set(partition_ids) or len(source_ids) != len(partition_ids):
        raise ReconciliationError(
            "订单一级分区行数或源行集合不守恒",
            code="ORDER_PARTITION_NOT_CONSERVED",
        )


def partition_orders(table: LoadedTable, config: RunConfig) -> OrderPartitions:
    """执行 P4 清洗、期间过滤、分类和源行守恒校验。"""

    retained, deleted = apply_cleaning_rules(table)
    in_period, out_of_period = filter_period(retained, config)
    classified, classification_issues = classify_orders(in_period)
    result = OrderPartitions(
        deleted=deleted,
        out_of_period=out_of_period,
        normal=classified[OrderPartition.NORMAL_CODED],
        closed_shipped=classified[OrderPartition.CLOSED_SHIPPED_CODED],
        missing_merchant_code=classified[OrderPartition.MISSING_MERCHANT_CODE],
        other_status=classified[OrderPartition.OTHER_STATUS],
        issues=tuple(table.issues) + classification_issues,
    )
    _assert_partition_conservation(table.data, result)
    return result
