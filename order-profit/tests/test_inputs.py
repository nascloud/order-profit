from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from order_profit.errors import InputContractError
from order_profit.inputs import ORDER_COLUMNS, load_orders, load_promotion


def _valid_order_data() -> dict[str, list[object]]:
    return {column: [""] for column in sorted(ORDER_COLUMNS)}


def test_load_orders_trims_headers_and_records_metadata(tmp_path: Path) -> None:
    path = tmp_path / "orders.xlsx"
    data = _valid_order_data()
    data["主订单编号"] = ["001"]
    renamed = data.pop("商品ID")
    data[" 商品ID "] = renamed
    pd.DataFrame(data).to_excel(path, sheet_name="export", index=False)

    loaded = load_orders(path)

    assert "商品ID" in loaded.data.columns
    assert loaded.metadata.rows == 1
    assert len(loaded.metadata.sha256) == 64


def test_load_orders_skips_fully_empty_layout_rows_but_preserves_source_row(tmp_path: Path) -> None:
    path = tmp_path / "orders.xlsx"
    data = _valid_order_data()
    first = {column: ("001" if column == "主订单编号" else "") for column in data}
    empty = {column: None for column in data}
    second = {column: ("002" if column == "主订单编号" else "") for column in data}
    frame = pd.DataFrame([first, empty, second])
    frame.to_excel(path, sheet_name="export", index=False)

    loaded = load_orders(path)

    assert loaded.metadata.rows == 2
    assert any(issue.code == "INPUT_EMPTY_ROWS_SKIPPED" for issue in loaded.issues)


def test_load_orders_rejects_missing_sheet(tmp_path: Path) -> None:
    path = tmp_path / "orders.xlsx"
    pd.DataFrame(_valid_order_data()).to_excel(path, sheet_name="wrong", index=False)

    with pytest.raises(InputContractError, match="缺少工作表"):
        load_orders(path)


def test_load_orders_rejects_duplicate_headers_after_trimming(tmp_path: Path) -> None:
    path = tmp_path / "orders.xlsx"
    columns = list(sorted(ORDER_COLUMNS)) + [" 商品ID "]
    pd.DataFrame([[""] * len(columns)], columns=columns).to_excel(
        path, sheet_name="export", index=False
    )

    with pytest.raises(InputContractError, match="重复"):
        load_orders(path)


def test_promotion_falls_back_to_gb18030(tmp_path: Path) -> None:
    path = tmp_path / "promotion.csv"
    data = pd.DataFrame(
        {
            "日期": ["2026-08-01"],
            "主体ID": ["123"],
            "主体名称": ["测试商品"],
            "展现量": [1],
            "点击量": [1],
            "花费": ["1.00"],
            "总成交金额": ["2.00"],
            "总成交笔数": [1],
        }
    )
    data.to_csv(path, index=False, encoding="gb18030")

    loaded = load_promotion(path)

    assert loaded.metadata.encoding == "gb18030"
    assert loaded.metadata.rows == 1
