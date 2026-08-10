"""P1～P3 阶段的输入读取与校验流程。"""

from __future__ import annotations

from order_profit.config import RunConfig
from order_profit.inputs import (
    LoadedTable,
    load_after_sales,
    load_costs,
    load_freight,
    load_orders,
    load_promotion,
    load_supplements,
)
from order_profit.normalize import add_source_audit_columns, normalize_ids, normalize_merchant_code
from order_profit.validation import normalize_loaded_tables


ID_COLUMNS_BY_ROLE: dict[str, list[str]] = {
    "orders": ["主订单编号", "商品ID", "物流单号"],
    "freight": ["运单号", "订单编码"],
    "after_sales": ["订单编号", "退款编号"],
    "promotion": ["主体ID"],
    "supplements": ["主订单编号", "商品ID"],
}
MERCHANT_CODE_COLUMNS: dict[str, str] = {
    "orders": "商家编码",
    "costs": "编码",
    "supplements": "商家编码",
}


def _apply_safe_normalization(role: str, table: LoadedTable) -> LoadedTable:
    data = add_source_audit_columns(
        table.data,
        path=table.metadata.path,
        sheet=table.metadata.sheet,
        file_sha256=table.metadata.sha256,
    )
    id_columns = [column for column in ID_COLUMNS_BY_ROLE.get(role, []) if column in data.columns]
    if id_columns:
        data = normalize_ids(data, id_columns)
    merchant_column = MERCHANT_CODE_COLUMNS.get(role)
    if merchant_column is not None and merchant_column in data.columns:
        data[merchant_column] = data[merchant_column].map(normalize_merchant_code)
    return LoadedTable(data=data, metadata=table.metadata, issues=table.issues)


def validate_inputs(config: RunConfig) -> dict[str, LoadedTable]:
    """读取并验证本次启用的所有输入，不执行 P4 之后的业务计算。"""

    loaded: dict[str, LoadedTable] = {
        "orders": load_orders(config.orders, config.orders_sheet),
    }
    if config.costs is not None:
        loaded["costs"] = load_costs(config.costs, config.costs_sheet)
    if config.freight is not None:
        loaded["freight"] = load_freight(config.freight, config.freight_sheet)
    if config.after_sales is not None:
        loaded["after_sales"] = load_after_sales(config.after_sales, config.after_sales_sheet)
    if config.promotion is not None:
        loaded["promotion"] = load_promotion(config.promotion)
    if config.supplements is not None:
        loaded["supplements"] = load_supplements(config.supplements, config.supplements_sheet)
    safely_normalized = {
        role: _apply_safe_normalization(role, table) for role, table in loaded.items()
    }
    return normalize_loaded_tables(safely_normalized, config)
