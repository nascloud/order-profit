from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from order_profit.config import Platform, RunConfig
from order_profit.errors import InputContractError
from order_profit.inputs import LoadedTable
from order_profit.models import InputFileMetadata
from order_profit.normalize import add_source_audit_columns
from order_profit.validation import normalize_costs, normalize_orders


def _config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        orders=tmp_path / "orders.xlsx",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        platform=Platform.TMALL,
        output_dir=tmp_path / "output",
    )


def _cost_table(tmp_path: Path, data: pd.DataFrame) -> LoadedTable:
    path = tmp_path / "costs.xlsx"
    audited = add_source_audit_columns(
        data,
        path=path,
        sheet="Sheet1",
        file_sha256="a" * 64,
    )
    metadata = InputFileMetadata(
        role="成本编码表",
        path=path,
        sha256="a" * 64,
        size_bytes=1,
        rows=len(data),
        sheet="Sheet1",
    )
    return LoadedTable(data=audited, metadata=metadata)


def _order_table_without_cost_or_freight(tmp_path: Path) -> LoadedTable:
    path = tmp_path / "orders.xlsx"
    data = pd.DataFrame(
        [
            {
                "主订单编号": "O1",
                "商品ID": "P1",
                "商品标题": "测试商品",
                "商品属性": "颜色:白色",
                "购买数量": 2,
                "订单状态": "交易成功",
                "商家编码": "SKU1",
                "买家应付货款": "20.00",
                "退款状态": "无退款",
                "退款金额": None,
                "订单付款时间": "2026-08-01 12:00:00",
                "商家备注": "",
                "物流单号": "W1",
            }
        ]
    )
    audited = add_source_audit_columns(
        data,
        path=path,
        sheet="export",
        file_sha256="b" * 64,
    )
    metadata = InputFileMetadata(
        role="订单表",
        path=path,
        sha256="b" * 64,
        size_bytes=1,
        rows=1,
        sheet="export",
    )
    return LoadedTable(data=audited, metadata=metadata)


def test_normalize_orders_creates_empty_internal_cost_and_freight_columns(
    tmp_path: Path,
) -> None:
    normalized = normalize_orders(
        _order_table_without_cost_or_freight(tmp_path),
        _config(tmp_path),
    )

    row = normalized.data.iloc[0]
    assert row["货品成本_分"] is None
    assert row["运费_分"] is None
    assert "货品成本" not in normalized.data.columns
    assert "运费" not in normalized.data.columns


def test_costs_drop_identical_duplicate_codes(tmp_path: Path) -> None:
    table = _cost_table(
        tmp_path,
        pd.DataFrame({"编码": ["A", "A"], "成本": ["1.00", "1.00"], "运费": ["2", "2"]}),
    )

    normalized = normalize_costs(table, _config(tmp_path))

    assert len(normalized.data) == 1
    assert normalized.data.iloc[0]["成本_分"] == 100


def test_costs_reject_conflicting_duplicate_codes(tmp_path: Path) -> None:
    table = _cost_table(
        tmp_path,
        pd.DataFrame({"编码": ["A", "A"], "成本": ["1.00", "1.01"], "运费": ["2", "2"]}),
    )

    with pytest.raises(InputContractError, match="冲突"):
        normalize_costs(table, _config(tmp_path))


def test_costs_reject_conflicting_product_names(tmp_path: Path) -> None:
    table = _cost_table(tmp_path, pd.DataFrame({
        "编码": ["SKU1", "SKU1"], "成本": ["1.00", "1.00"], "运费": ["2.00", "2.00"], "产品名称": ["产品A", "产品B"],
    }))
    with pytest.raises(InputContractError, match="冲突核算值"):
        normalize_costs(table, _config(tmp_path))


def test_costs_reject_empty_code(tmp_path: Path) -> None:
    table = _cost_table(
        tmp_path,
        pd.DataFrame({"编码": [""], "成本": ["1.00"], "运费": ["2"]}),
    )

    with pytest.raises(InputContractError, match="编码不能为空"):
        normalize_costs(table, _config(tmp_path))
