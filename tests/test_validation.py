from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from order_profit.config import Platform, RunConfig
from order_profit.errors import InputContractError
from order_profit.inputs import LoadedTable
from order_profit.models import InputFileMetadata, Severity
from order_profit.normalize import add_source_audit_columns
from order_profit.validation import normalize_costs, normalize_freight, normalize_orders


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


def _freight_table(tmp_path: Path, data: pd.DataFrame) -> LoadedTable:
    path = tmp_path / "freight.xlsx"
    audited = add_source_audit_columns(
        data,
        path=path,
        sheet="运费明细",
        file_sha256="c" * 64,
    )
    metadata = InputFileMetadata(
        role="运费表",
        path=path,
        sha256="c" * 64,
        size_bytes=1,
        rows=len(data),
        sheet="运费明细",
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


@pytest.mark.parametrize(
    ("order_code", "order_id"),
    [
        (" 3316502714015000499_DPK301941292143 ", "3316502714015000499"),
        (" 0003316502714015000499 _child_extra ", "0003316502714015000499"),
        (" 0003316502714015000499 ", "0003316502714015000499"),
    ],
)
def test_freight_extracts_string_order_id_and_preserves_order_code(
    tmp_path: Path, order_code: str, order_id: str,
) -> None:
    table = _freight_table(
        tmp_path,
        pd.DataFrame({"运单号": ["W1"], "订单编码": [order_code], "总运费": ["1.23"]}),
    )

    normalized = normalize_freight(table, _config(tmp_path))

    row = normalized.data.iloc[0]
    assert isinstance(row["主订单编号"], str)
    assert row["主订单编号"] == order_id
    assert row["订单编码"] == order_code
    assert row["运单号"] == "W1"
    assert row["总运费_分"] == 123
    assert row["source_row_id"] == table.data.iloc[0]["source_row_id"]
    assert table.data.iloc[0]["订单编码"] == order_code


def test_freight_preserves_independent_waybills_and_zero_child_rows(
    tmp_path: Path,
) -> None:
    table = _freight_table(
        tmp_path,
        pd.DataFrame({
            "运单号": ["W1", "W2", "W3"],
            "订单编码": ["000123_parent", "000123_child", "000123_other"],
            "总运费": ["3.21", "0", "1.11"],
        }),
    )

    normalized = normalize_freight(table, _config(tmp_path))

    assert len(normalized.data) == 3
    assert normalized.data.set_index("运单号")["主订单编号"].to_dict() == {
        "W1": "000123", "W2": "000123", "W3": "000123",
    }
    assert normalized.data.set_index("运单号")["总运费_分"].to_dict() == {
        "W1": 321, "W2": 0, "W3": 111,
    }
    assert normalized.data["总运费_分"].sum() == 432
    assert set(normalized.data["source_row_id"]) == set(table.data["source_row_id"])


def test_freight_deduplicates_same_waybill_order_and_amount(tmp_path: Path) -> None:
    table = _freight_table(
        tmp_path,
        pd.DataFrame({
            "运单号": ["W1", "W1", "W1"],
            "订单编码": ["000123_parent", "000123_parent", " 000123 _child"],
            "总运费": ["2", "2.00", "2.0"],
        }),
    )

    normalized = normalize_freight(table, _config(tmp_path))

    assert len(normalized.data) == 1
    row = normalized.data.iloc[0]
    assert row["运单号"] == "W1"
    assert row["主订单编号"] == "000123"
    assert row["总运费_分"] == 200
    assert row["source_row_id"] in set(table.data["source_row_id"])


@pytest.mark.parametrize(
    ("order_codes", "amounts"),
    [
        (["000123_parent", "000123_child"], ["2.00", "2.01"]),
        (["000123_parent", "000124_child"], ["2.00", "2.00"]),
        (["000123_parent", "123_child"], ["2.00", "2.00"]),
    ],
)
def test_freight_rejects_conflicting_waybill_order_or_amount(
    tmp_path: Path, order_codes: list[str], amounts: list[str],
) -> None:
    table = _freight_table(
        tmp_path,
        pd.DataFrame({"运单号": ["W1", "W1"], "订单编码": order_codes, "总运费": amounts}),
    )

    with pytest.raises(InputContractError) as caught:
        normalize_freight(table, _config(tmp_path))

    assert caught.value.code == "FREIGHT_WAYBILL_CONFLICT"


@pytest.mark.parametrize("order_code", ["", None, "   ", "_000123", "  _000123_child"])
def test_freight_retains_missing_order_id_with_located_warning(
    tmp_path: Path, order_code: str | None,
) -> None:
    table = _freight_table(
        tmp_path,
        pd.DataFrame(
            {
                "运单号": ["000123"],
                "订单编码": [order_code],
                "总运费": ["1.23"],
            },
            index=[7],
        ),
    )

    normalized = normalize_freight(table, _config(tmp_path))

    assert len(normalized.data) == 1
    row = normalized.data.iloc[0]
    assert row["主订单编号"] == ""
    assert row["订单编码"] == order_code
    assert row["运单号"] == "000123"
    assert row["总运费_分"] == 123
    assert row["source_row_id"] == table.data.iloc[0]["source_row_id"]
    issues = [issue for issue in normalized.issues if issue.code == "FREIGHT_ORDER_ID_MISSING"]
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == Severity.WARNING
    assert issue.location.file == str(table.metadata.path.resolve())
    assert issue.location.sheet == "运费明细"
    assert issue.location.row == 9
    assert issue.location.field == "订单编码"


@pytest.mark.parametrize(
    ("amount", "error_code"),
    [("", "MONEY_REQUIRED"), (None, "MONEY_REQUIRED"), ("-0.01", "MONEY_NEGATIVE")],
)
@pytest.mark.parametrize("order_code", ["000123_child", ""])
def test_freight_requires_nonnegative_amount_even_without_order_id(
    tmp_path: Path, amount: str | None, error_code: str, order_code: str,
) -> None:
    table = _freight_table(
        tmp_path,
        pd.DataFrame({"运单号": ["W1"], "订单编码": [order_code], "总运费": [amount]}),
    )

    with pytest.raises(InputContractError) as caught:
        normalize_freight(table, _config(tmp_path))

    assert caught.value.code == error_code
    issue = caught.value.issues[0]
    assert issue.location.file == str(table.metadata.path.resolve())
    assert issue.location.sheet == "运费明细"
    assert issue.location.row == 2
    assert issue.location.field == "总运费"
