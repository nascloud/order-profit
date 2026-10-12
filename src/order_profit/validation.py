"""表级严格标准化和 P2/P3 输入内一致性校验。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from order_profit.config import RunConfig
from order_profit.errors import InputContractError
from order_profit.inputs import LoadedTable
from order_profit.models import Issue, Severity, SourceLocation
from order_profit.normalize import (
    is_missing,
    money_to_cents,
    normalize_count,
    normalize_datetime,
    normalize_merchant_code,
    normalize_quantity,
)


Transform = Callable[..., Any]


def _location(data: pd.DataFrame, index: Any, field: str) -> SourceLocation:
    return SourceLocation(
        file=data.attrs.get("source_path"),
        sheet=(data.at[index, "source_sheet"] if "source_sheet" in data else None),
        row=(int(data.at[index, "source_row_number"]) if "source_row_number" in data else None),
        field=field,
    )


def _map_column(
    data: pd.DataFrame,
    source: str,
    target: str,
    transform: Transform,
    **kwargs: Any,
) -> None:
    data[target] = [
        transform(value, location=_location(data, index, source), **kwargs)
        for index, value in data[source].items()
    ]


def _require_nonempty_key(data: pd.DataFrame, *, column: str, role: str) -> None:
    mask = data[column] == ""
    if mask.any():
        rows = data.loc[mask, "source_row_number"].astype(int).tolist()[:10]
        raise InputContractError(
            f"{role}的{column}不能为空，源行：{rows}",
            code="INPUT_KEY_EMPTY",
            issues=[
                Issue(
                    code="INPUT_KEY_EMPTY",
                    severity=Severity.ERROR,
                    message=f"{column}是必需匹配键，不能为空",
                    location=SourceLocation(
                        file=data.attrs.get("source_path"),
                        sheet=(
                            str(data.loc[mask, "source_sheet"].iloc[0])
                            if "source_sheet" in data and rows
                            else None
                        ),
                        row=rows[0] if rows else None,
                        field=column,
                    ),
                    raw_value="（空）",
                    suggestion="请补齐匹配键或删除无效行后重试",
                )
            ],
        )


def _raise_duplicate_conflict(
    data: pd.DataFrame,
    *,
    key: str,
    value_columns: list[str],
    role: str,
    code: str,
) -> pd.DataFrame:
    """去完全重复；同键对应不同核算字段时失败。"""

    deduplicated = data.drop_duplicates().copy()
    nonempty = deduplicated[deduplicated[key] != ""]
    conflicts: list[str] = []
    for key_value, group in nonempty.groupby(key, sort=False, dropna=False):
        if len(group[value_columns].drop_duplicates()) > 1:
            conflicts.append(str(key_value))
    if conflicts:
        sample = conflicts[:10]
        raise InputContractError(
            f"{role}同一{key}存在冲突核算值：{'、'.join(sample)}",
            code=code,
            issues=[
                Issue(
                    code=code,
                    severity=Severity.ERROR,
                    message=f"同一{key}存在不同核算值",
                    raw_value=sample,
                    suggestion="请修正冲突源数据后重试，程序不会静默选择第一条",
                )
            ],
        )
    return deduplicated.drop_duplicates(subset=[key], keep="first").copy()


def normalize_orders(table: LoadedTable, config: RunConfig) -> LoadedTable:
    data = table.data.copy()
    # 付款时间的必填性依赖 P4：已被清洗删除的行允许缺失。
    _map_column(
        data,
        "订单付款时间",
        "订单付款时间_标准",
        normalize_datetime,
        timezone=config.timezone,
        allow_missing=True,
    )
    # 原始订单导出不包含成本和运费；统一创建内部空值列，后续分别从
    # 成本编码表、运费表或人工补充表解析。
    data["货品成本_分"] = pd.Series([None] * len(data), index=data.index, dtype=object)
    data["运费_分"] = pd.Series([None] * len(data), index=data.index, dtype=object)

    # 购买数量、货款和退款的必填性依赖 P4 清洗与分类；这里只拒绝非空非法值。
    data["购买数量_标准"] = [
        normalize_quantity(
            value,
            allow_missing=True,
            location=_location(data, index, "购买数量"),
        )
        for index, value in data["购买数量"].items()
    ]
    data["买家应付货款_分"] = [
        money_to_cents(
            value,
            allow_missing=True,
            location=_location(data, index, "买家应付货款"),
        )
        for index, value in data["买家应付货款"].items()
    ]
    refund_values: list[int | None] = []
    for index, value in data["退款金额"].items():
        if isinstance(value, str) and value.strip() == "无退款申请":
            value = None
        refund_values.append(
            money_to_cents(
                value,
                allow_missing=True,
                nonnegative=True,
                location=_location(data, index, "退款金额"),
            )
        )
    data["退款金额_分"] = refund_values
    return LoadedTable(data=data, metadata=table.metadata, issues=table.issues)


def normalize_costs(table: LoadedTable, config: RunConfig) -> LoadedTable:
    del config
    data = table.data.copy()
    _require_nonempty_key(data, column="编码", role="成本编码表")
    _map_column(data, "成本", "成本_分", money_to_cents, nonnegative=True)
    _map_column(data, "运费", "运费_分", money_to_cents, nonnegative=True)
    if "产品名称" not in data.columns:
        data["产品名称"] = ""
    data["产品名称"] = data["产品名称"].fillna("").map(lambda value: str(value).strip())
    data = _raise_duplicate_conflict(
        data,
        key="编码",
        value_columns=["成本_分", "运费_分", "产品名称"],
        role="成本编码表",
        code="COST_CODE_CONFLICT",
    )
    return LoadedTable(data=data, metadata=table.metadata, issues=table.issues)


def normalize_freight(table: LoadedTable, config: RunConfig) -> LoadedTable:
    del config
    data = table.data.copy().drop_duplicates()
    _require_nonempty_key(data, column="运单号", role="运费表")
    data["主订单编号"] = data["订单编码"].map(
        lambda value: "" if is_missing(value) else str(value).partition("_")[0].strip()
    )
    _map_column(data, "总运费", "总运费_分", money_to_cents, nonnegative=True)
    data = _raise_duplicate_conflict(
        data,
        key="运单号",
        value_columns=["主订单编号", "总运费_分"],
        role="运费表",
        code="FREIGHT_WAYBILL_CONFLICT",
    )
    issues = list(table.issues)
    for index in data.index[data["主订单编号"].eq("")]:
        issues.append(
            Issue(
                code="FREIGHT_ORDER_ID_MISSING",
                severity=Severity.WARNING,
                message="运费表订单编码无法提取订单号，该行不参与实际运费匹配",
                location=_location(data, index, "订单编码"),
                raw_value=data.at[index, "订单编码"],
                suggestion="补齐订单编码中的订单号后重新核算",
            )
        )
    return LoadedTable(data=data, metadata=table.metadata, issues=tuple(issues))


def normalize_after_sales(table: LoadedTable, config: RunConfig) -> LoadedTable:
    data = table.data.copy().drop_duplicates()
    _require_nonempty_key(data, column="退款编号", role="售后表")
    _map_column(data, "退款总额", "退款总额_分", money_to_cents, nonnegative=True)
    _map_column(
        data,
        "退款完结时间",
        "退款完结时间_标准",
        normalize_datetime,
        timezone=config.timezone,
        allow_missing=True,
    )
    data = _raise_duplicate_conflict(
        data,
        key="退款编号",
        value_columns=["订单编号", "退款状态", "退款总额_分", "退款完结时间_标准"],
        role="售后表",
        code="AFTER_SALES_REFUND_CONFLICT",
    )
    return LoadedTable(data=data, metadata=table.metadata, issues=table.issues)


def normalize_promotion(table: LoadedTable, config: RunConfig) -> LoadedTable:
    data = table.data.copy()
    _map_column(data, "日期", "日期_标准", normalize_datetime, timezone=config.timezone)
    for source, target in (("花费", "花费_分"), ("总成交金额", "总成交金额_分")):
        _map_column(data, source, target, money_to_cents, allow_missing=True, nonnegative=True)
        data[target] = data[target].fillna(0).astype(object)
    for column in ("展现量", "点击量", "总成交笔数"):
        normalized: list[int] = []
        for index, value in data[column].items():
            if is_missing(value):
                normalized.append(0)
                continue
            count = normalize_count(value, location=_location(data, index, column))
            normalized.append(count)
        data[f"{column}_标准"] = normalized
    business_columns = [
        column
        for column in table.data.columns
        if not column.startswith("source_")
    ]
    duplicate_count = int(table.data.duplicated(subset=business_columns).sum())
    issues = list(table.issues)
    if duplicate_count:
        issues.append(
            Issue(
                code="PROMOTION_EXACT_DUPLICATES",
                severity=Severity.WARNING,
                message=f"推广报表存在 {duplicate_count} 条完全重复行；首版保留并报告",
                location=SourceLocation(file=str(table.metadata.path)),
            )
        )
    return LoadedTable(data=data, metadata=table.metadata, issues=tuple(issues))


def normalize_supplements(table: LoadedTable, config: RunConfig) -> LoadedTable:
    del config
    data = table.data.copy()
    keys = ["主订单编号", "商品ID", "商家编码"]
    for key in ("主订单编号", "商品ID"):
        _require_nonempty_key(data, column=key, role="人工补充表")
    if "补充商家编码" not in data.columns:
        data["补充商家编码"] = ""
    data["商家编码"] = data["商家编码"].map(normalize_merchant_code)
    data["补充商家编码"] = data["补充商家编码"].map(normalize_merchant_code)
    if "明细序号" not in data.columns:
        data["明细序号"] = None
    detail_numbers: list[int | None] = []
    for index, value in data["明细序号"].items():
        if is_missing(value):
            detail_numbers.append(None)
            continue
        number = normalize_count(value, location=_location(data, index, "明细序号"))
        if number < 2:
            raise InputContractError(
                "人工补充表明细序号必须是原订单 Excel 数据行号（不小于 2）",
                code="SUPPLEMENT_DETAIL_ROW_INVALID",
            )
        detail_numbers.append(number)
    data["明细序号"] = pd.Series(detail_numbers, index=data.index, dtype=object)
    allowed = {"", "已确认", "已同步", "草稿", "作废"}
    data["补充状态"] = data["补充状态"].fillna("").map(lambda value: str(value).strip())
    invalid = sorted(set(data.loc[~data["补充状态"].isin(allowed), "补充状态"]))
    if invalid:
        raise InputContractError(
            f"人工补充表存在未知补充状态：{'、'.join(invalid)}",
            code="SUPPLEMENT_STATUS_INVALID",
        )
    _map_column(data, "货品成本", "货品成本_分", money_to_cents, allow_missing=True, nonnegative=True)
    _map_column(data, "运费", "运费_分", money_to_cents, allow_missing=True, nonnegative=True)
    both_money_missing = data["货品成本_分"].isna() & data["运费_分"].isna()
    code_missing = data["补充商家编码"].eq("")
    active = data["补充状态"].isin({"", "已确认", "已同步"})
    invalid_empty = both_money_missing & code_missing & active
    if invalid_empty.any():
        rows = data.loc[invalid_empty, "source_row_number"].astype(int).tolist()[:10]
        raise InputContractError(
            f"生效的人工补充行必须填写成本或运费，源行：{rows}",
            code="SUPPLEMENT_VALUES_EMPTY",
        )
    incomplete_without_code = (
        data["商家编码"].eq("")
        & data["补充商家编码"].eq("")
        & (data["货品成本_分"].isna() | data["运费_分"].isna())
        & active
    )
    if incomplete_without_code.any():
        rows = data.loc[incomplete_without_code, "source_row_number"].astype(int).tolist()[:10]
        raise InputContractError(
            f"原商家编码为空的生效补充行必须同时填写成本和运费，源行：{rows}",
            code="SUPPLEMENT_CODELESS_AMOUNTS_INCOMPLETE",
        )
    missing_original_code_without_detail = (
        data["商家编码"].eq("")
        & data["补充商家编码"].ne("")
        & data["明细序号"].isna()
    )
    if missing_original_code_without_detail.any():
        rows = data.loc[missing_original_code_without_detail, "source_row_number"].astype(int).tolist()[:10]
        raise InputContractError(
            f"补充缺失商家编码时必须提供明细序号，源行：{rows}",
            code="SUPPLEMENT_CODE_DETAIL_REQUIRED",
        )
    data["_补充唯一键"] = [
        (*tuple(str(row[key]) for key in keys), row["明细序号"])
        for _, row in data.iterrows()
    ]
    duplicated = data["_补充唯一键"].duplicated(keep=False)
    if duplicated.any():
        sample_columns = keys + ["明细序号"]
        sample = data.loc[duplicated, sample_columns].head(10).to_dict("records")
        raise InputContractError(
            f"人工补充键重复：{sample}",
            code="SUPPLEMENT_KEY_DUPLICATE",
        )
    data = data.drop(columns=["_补充唯一键"])
    return LoadedTable(data=data, metadata=table.metadata, issues=table.issues)


NORMALIZERS: dict[str, Callable[[LoadedTable, RunConfig], LoadedTable]] = {
    "orders": normalize_orders,
    "costs": normalize_costs,
    "freight": normalize_freight,
    "after_sales": normalize_after_sales,
    "promotion": normalize_promotion,
    "supplements": normalize_supplements,
}


def normalize_loaded_tables(
    tables: dict[str, LoadedTable], config: RunConfig
) -> dict[str, LoadedTable]:
    return {role: NORMALIZERS[role](table, config) for role, table in tables.items()}
