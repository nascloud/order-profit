"""人工补充、货品成本与运费解析。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import pandas as pd

from order_profit.errors import InputContractError
from order_profit.inputs import LoadedTable
from order_profit.models import Issue, Severity, SourceLocation
from order_profit.normalize import is_missing
from order_profit.rules import NORMAL_STATUSES, OrderPartitions, is_brush_order

SUPPLEMENT_KEYS: Final[list[str]] = ["主订单编号", "商品ID", "商家编码"]
ACTIVE_SUPPLEMENT_STATUSES: Final[frozenset[str]] = frozenset({"", "已确认", "已同步"})


@dataclass(frozen=True, slots=True)
class SupplementResult:
    orders: LoadedTable
    audit: pd.DataFrame


@dataclass(frozen=True, slots=True)
class CostResolutionResult:
    normal: pd.DataFrame
    closed_shipped: pd.DataFrame
    supplement_audit: pd.DataFrame
    closed_unshipped: pd.DataFrame = field(default_factory=pd.DataFrame)
    issues: tuple[Issue, ...] = ()

    @property
    def missing_cost_rows(self) -> int:
        return int(self.normal["核算成本_分"].isna().sum()) + int(
            self.closed_shipped["核算成本_分"].isna().sum()
        )

    @property
    def missing_freight_rows(self) -> int:
        return int(self.normal["核算运费_分"].isna().sum()) + int(
            self.closed_shipped["核算运费_分"].isna().sum()
        )


def _location(row: pd.Series, field: str) -> SourceLocation:
    source_row = row.get("source_row_number")
    return SourceLocation(
        file=row.attrs.get("source_path"),
        sheet=(str(row.get("source_sheet")) if not is_missing(row.get("source_sheet")) else None),
        row=(int(source_row) if not is_missing(source_row) else None),
        field=field,
    )


def _key_tuple(row: pd.Series) -> tuple[str, str, str]:
    return tuple(str(row[column]) for column in SUPPLEMENT_KEYS)  # type: ignore[return-value]


def _apply_supplement_field(
    result: pd.DataFrame,
    *,
    target_index: object,
    supplement_value: object,
    existing_value: object,
    target_column: str,
    overwrite_existing: bool,
) -> tuple[bool, str]:
    if is_missing(supplement_value):
        return False, "补充字段为空"
    if not overwrite_existing and not is_missing(existing_value):
        return False, "目标已有值且未启用覆盖"
    result.at[target_index, target_column] = int(supplement_value)
    return True, "已应用"


def apply_supplements(
    orders: LoadedTable,
    supplements: LoadedTable | None,
    *,
    overwrite_existing: bool,
) -> SupplementResult:
    """在全量标准化源订单上匹配补充，保留字段级应用审计。"""

    result = orders.data.copy()
    result.attrs.update(orders.data.attrs)
    result["补充货品成本_分"] = pd.Series([None] * len(result), index=result.index, dtype=object)
    result["补充运费_分"] = pd.Series([None] * len(result), index=result.index, dtype=object)
    result["补充记录源行"] = pd.Series([None] * len(result), index=result.index, dtype=object)

    if supplements is None:
        return SupplementResult(
            orders=LoadedTable(result, orders.metadata, orders.issues),
            audit=pd.DataFrame(),
        )

    order_key_groups: dict[tuple[str, str, str], list[object]] = {}
    for index, row in result.iterrows():
        order_key_groups.setdefault(_key_tuple(row), []).append(index)

    audit_rows: list[dict[str, object]] = []
    for _, supplement in supplements.data.iterrows():
        key = _key_tuple(supplement)
        matched = order_key_groups.get(key, [])
        detail_number = supplement.get("明细序号")
        if not is_missing(detail_number):
            matched = [
                index
                for index in matched
                if int(result.at[index, "source_row_number"]) == int(detail_number)
            ]
        if not matched:
            issue = Issue(
                code="SUPPLEMENT_TARGET_NOT_FOUND",
                severity=Severity.ERROR,
                message="人工补充记录找不到任何源订单",
                location=_location(supplement, "主订单编号"),
                raw_value=dict(zip(SUPPLEMENT_KEYS, key, strict=True)),
                suggestion="核对主订单编号、商品ID和商家编码，匹配在全量源订单中执行",
            )
            raise InputContractError(issue.message, code=issue.code, issues=[issue])
        if len(matched) > 1:
            issue = Issue(
                code="SUPPLEMENT_TARGET_NOT_UNIQUE",
                severity=Severity.ERROR,
                message="人工补充键匹配到多条源订单明细",
                location=_location(supplement, "主订单编号"),
                raw_value={"key": key, "matched_source_rows": matched},
                suggestion="补充表需增加可唯一定位的明细序号后再运行",
            )
            raise InputContractError(issue.message, code=issue.code, issues=[issue])

        target_index = matched[0]
        status = str(supplement["补充状态"])
        active = status in ACTIVE_SUPPLEMENT_STATUSES
        applied_code = False
        code_reason = "状态不生效"
        applied_cost = False
        applied_freight = False
        cost_reason = "状态不生效"
        freight_reason = "状态不生效"
        if active:
            supplemental_code = str(supplement.get("补充商家编码", "")).strip()
            existing_code = str(result.at[target_index, "商家编码"]).strip()
            if supplemental_code:
                if existing_code:
                    issue = Issue(
                        code="SUPPLEMENT_CODE_OVERWRITE_FORBIDDEN",
                        severity=Severity.ERROR,
                        message="已有商家编码的订单不允许通过补充表覆盖编码",
                        location=_location(supplement, "补充商家编码"),
                        raw_value={"existing": existing_code, "supplement": supplemental_code},
                        suggestion="清空补充商家编码；如编码确有错误，请修正源订单后重试",
                    )
                    raise InputContractError(issue.message, code=issue.code, issues=[issue])
                result.at[target_index, "商家编码"] = supplemental_code
                applied_code = True
                code_reason = "已应用"
            else:
                code_reason = "补充字段为空"
            applied_cost, cost_reason = _apply_supplement_field(
                result,
                target_index=target_index,
                supplement_value=supplement.get("货品成本_分"),
                existing_value=result.at[target_index, "补充货品成本_分"],
                target_column="补充货品成本_分",
                overwrite_existing=overwrite_existing,
            )
            applied_freight, freight_reason = _apply_supplement_field(
                result,
                target_index=target_index,
                supplement_value=supplement.get("运费_分"),
                existing_value=result.at[target_index, "补充运费_分"],
                target_column="补充运费_分",
                overwrite_existing=overwrite_existing,
            )
            result.at[target_index, "补充记录源行"] = int(supplement["source_row_number"])

        audit_rows.append(
            {
                **{column: supplement[column] for column in SUPPLEMENT_KEYS},
                "补充状态": status,
                "明细序号": (
                    int(detail_number) if not is_missing(detail_number) else None
                ),
                "补充表源行": int(supplement["source_row_number"]),
                "匹配订单源行": int(result.at[target_index, "source_row_number"]),
                "匹配订单分区": None,
                "编码已应用": applied_code,
                "编码处理原因": code_reason,
                "最终商家编码": str(result.at[target_index, "商家编码"]),
                "成本已应用": applied_cost,
                "成本处理原因": cost_reason,
                "运费已应用": applied_freight,
                "运费处理原因": freight_reason,
            }
        )

    audit = pd.DataFrame(audit_rows)
    return SupplementResult(
        orders=LoadedTable(result, orders.metadata, orders.issues),
        audit=audit,
    )


def _build_cost_lookup(costs: LoadedTable | None) -> dict[str, tuple[int, int, str]]:
    if costs is None:
        return {}
    return {
        str(row["编码"]): (int(row["成本_分"]), int(row["运费_分"]), str(row.get("产品名称", "")).strip())
        for _, row in costs.data.iterrows()
    }


def _build_freight_lookup(freight: LoadedTable | None) -> dict[str, int]:
    if freight is None:
        return {}
    rows = freight.data.loc[freight.data["主订单编号"].ne("")]
    return {
        str(order_id): int(total)
        for order_id, total in rows.groupby("主订单编号", sort=False)["总运费_分"].sum().items()
    }


def _allocate_cents(total: int, rows: pd.DataFrame) -> dict[int, int]:
    """按购买数量分摊整数分，尾差按余数和源行号确定性分配。"""

    weighted: list[tuple[int, int, int]] = []
    total_quantity = int(rows["购买数量_标准"].sum())
    for _, row in rows.iterrows():
        source_row = int(row["source_row_number"])
        quantity = int(row["购买数量_标准"])
        amount, remainder = divmod(total * quantity, total_quantity)
        weighted.append((source_row, amount, remainder))
    remainder_cents = total - sum(amount for _, amount, _ in weighted)
    priority = sorted(weighted, key=lambda item: (-item[2], item[0]))
    extra_rows = {source_row for source_row, _, _ in priority[:remainder_cents]}
    return {
        source_row: amount + (1 if source_row in extra_rows else 0)
        for source_row, amount, _ in weighted
    }


def _build_freight_plan(
    partitions: OrderPartitions,
    freight_lookup: dict[str, int],
) -> dict[int, tuple[int, str]]:
    """按主订单为有效明细分配实际总运费及来源。"""

    normal = partitions.normal.loc[
        [
            not (str(row.get("订单状态", "")) in NORMAL_STATUSES and is_brush_order(row))
            for _, row in partitions.normal.iterrows()
        ]
    ].copy()
    normal["_订单类型"] = "正常订单"
    closed = partitions.closed_shipped.copy()
    closed["_订单类型"] = "关闭已发货"
    rows = pd.concat([normal, closed], ignore_index=True)
    plan: dict[int, tuple[int, str]] = {}
    if rows.empty:
        return plan

    for order_id, group in rows.groupby("主订单编号", sort=False):
        actual = freight_lookup.get(str(order_id))
        if actual is None:
            continue
        source_rows = group["source_row_number"].astype(int).tolist()
        if len(group) == 1:
            plan[source_rows[0]] = (actual, "运费表实际运费")
            continue

        normal_rows = group[group["_订单类型"] == "正常订单"]
        recipients = normal_rows if not normal_rows.empty else group
        allocations = _allocate_cents(actual, recipients)
        for _, row in group.iterrows():
            source_row = int(row["source_row_number"])
            if source_row in allocations:
                plan[source_row] = (allocations[source_row], "同主订单运费按数量分摊")
            else:
                plan[source_row] = (0, "同主订单关闭明细不分摊")
    return plan


def _resolve_row(
    row: pd.Series,
    *,
    cost_lookup: dict[str, tuple[int, int, str]],
    freight_plan: dict[int, tuple[int, str]],
) -> tuple[dict[str, object], list[Issue]]:
    issues: list[Issue] = []
    code = str(row["商家编码"])
    quantity = int(row["购买数量_标准"])
    standard = cost_lookup.get(code)
    price_difference = bool(row.get("是否补差价专用", False))

    if str(row.get("订单状态", "")) in NORMAL_STATUSES and is_brush_order(row):
        return (
            {
                "产品名称": standard[2] if standard and standard[2] else "未归类",
                "核算成本_分": 0,
                "成本来源": "刷单业务规则",
                "核算运费_分": 0,
                "运费来源": "刷单业务规则",
                "成本运费状态": "已核算",
            },
            issues,
        )

    supplement_cost = row.get("补充货品成本_分")
    if price_difference:
        resolved_cost: int | None = 0
        cost_source = "补差价专用业务规则"
    elif standard is not None:
        resolved_cost = int(standard[0]) * quantity
        cost_source = "成本编码表"
    elif not is_missing(supplement_cost):
        resolved_cost = int(supplement_cost)
        cost_source = "人工补充"
    else:
        resolved_cost = None
        cost_source = "缺失"
        issues.append(
            Issue(
                code="ORDER_COST_MISSING",
                severity=Severity.WARNING,
                message="订单明细货品成本无法解析",
                location=_location(row, "商家编码"),
                raw_value=code,
                suggestion="在成本编码表或人工补充表中补齐成本",
            )
        )

    supplement_freight = row.get("补充运费_分")
    planned_freight = freight_plan.get(int(row["source_row_number"]))
    if planned_freight is not None:
        resolved_freight, freight_source = planned_freight
    elif standard is not None:
        resolved_freight = int(standard[1])
        freight_source = "成本编码表标准运费"
    elif not is_missing(supplement_freight):
        resolved_freight = int(supplement_freight)
        freight_source = "人工补充"
    elif price_difference:
        resolved_freight = 0
        freight_source = "补差价专用业务规则"
    else:
        resolved_freight = None
        freight_source = "缺失"
        issues.append(
            Issue(
                code="ORDER_FREIGHT_MISSING",
                severity=Severity.WARNING,
                message="订单明细运费无法解析",
                location=_location(row, "主订单编号"),
                raw_value=str(row["主订单编号"]),
                suggestion="检查运费表订单编码、成本编码表标准运费或人工补充表",
            )
        )

    return (
        {
            "产品名称": standard[2] if standard and standard[2] else "未归类",
            "核算成本_分": resolved_cost,
            "成本来源": cost_source,
            "核算运费_分": resolved_freight,
            "运费来源": freight_source,
            "成本运费状态": (
                "已核算" if resolved_cost is not None and resolved_freight is not None else "成本或运费缺失"
            ),
        },
        issues,
    )


def _resolve_frame(
    frame: pd.DataFrame,
    *,
    cost_lookup: dict[str, tuple[int, int, str]],
    freight_plan: dict[int, tuple[int, str]],
) -> tuple[pd.DataFrame, list[Issue]]:
    result = frame.copy()
    records: list[dict[str, object]] = []
    issues: list[Issue] = []
    for _, row in result.iterrows():
        resolved, row_issues = _resolve_row(
            row,
            cost_lookup=cost_lookup,
            freight_plan=freight_plan,
        )
        records.append(resolved)
        issues.extend(row_issues)
    if records:
        resolved_data = pd.DataFrame(records, index=result.index)
        for column in resolved_data.columns:
            result[column] = resolved_data[column]
    else:
        for column in (
            "核算成本_分",
            "成本来源",
            "核算运费_分",
            "运费来源",
            "成本运费状态",
        ):
            result[column] = pd.Series(index=result.index, dtype=object)
    return result, issues


def resolve_costs_and_freight(
    partitions: OrderPartitions,
    *,
    costs: LoadedTable | None,
    freight: LoadedTable | None,
    supplement_audit: pd.DataFrame,
) -> CostResolutionResult:
    """按规范优先级解析有效正常和关闭已发货订单的成本与运费。"""

    cost_lookup = _build_cost_lookup(costs)
    freight_lookup = _build_freight_lookup(freight)
    freight_plan = _build_freight_plan(partitions, freight_lookup)
    normal, normal_issues = _resolve_frame(
        partitions.normal,
        cost_lookup=cost_lookup,
        freight_plan=freight_plan,
    )
    closed, closed_issues = _resolve_frame(
        partitions.closed_shipped,
        cost_lookup=cost_lookup,
        freight_plan=freight_plan,
    )
    closed_unshipped = partitions.closed_unshipped.copy()
    if not closed_unshipped.empty:
        closed_unshipped["产品名称"] = closed_unshipped["商家编码"].map(
            lambda code: (cost_lookup.get(str(code), (0, 0, ""))[2] or "未归类")
        )
    closed_unshipped["核算成本_分"] = 0
    closed_unshipped["成本来源"] = "付款后关闭且无物流业务规则"
    closed_unshipped["核算运费_分"] = 0
    closed_unshipped["运费来源"] = "付款后关闭且无物流业务规则"
    closed_unshipped["成本运费状态"] = "已核算"

    audit = supplement_audit.copy()
    if not audit.empty:
        partition_by_row = {
            int(row["source_row_number"]): partition.value
            for partition, frame in partitions.as_dict().items()
            for _, row in frame.iterrows()
        }
        audit["匹配订单分区"] = audit["匹配订单源行"].map(partition_by_row)

    return CostResolutionResult(
        normal=normal,
        closed_shipped=closed,
        supplement_audit=audit,
        closed_unshipped=closed_unshipped,
        issues=tuple(partitions.issues) + tuple(normal_issues) + tuple(closed_issues),
    )
