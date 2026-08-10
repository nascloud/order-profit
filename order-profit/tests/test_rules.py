from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from order_profit.config import Platform, RunConfig
from order_profit.errors import NormalizationError
from order_profit.inputs import LoadedTable
from order_profit.models import InputFileMetadata
from order_profit.rules import (
    CleaningReason,
    OrderPartition,
    apply_cleaning_rules,
    partition_orders,
)

TZ = ZoneInfo("Asia/Shanghai")


def _config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        orders=tmp_path / "orders.xlsx",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        platform=Platform.TMALL,
        output_dir=tmp_path / "output",
    )


def _row(number: int, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "source_file_id": "a" * 16,
        "source_sheet": "export",
        "source_row_number": number,
        "source_row_id": f"{'a' * 16}:export:{number}",
        "主订单编号": f"O{number}",
        "商品ID": f"P{number}",
        "订单状态": "交易成功",
        "商家编码": f"SKU{number}",
        "买家应付货款": "20.00",
        "买家应付货款_分": 2000,
        "退款状态": "无退款",
        "退款金额": None,
        "退款金额_分": None,
        "订单付款时间": "2026-08-01 00:00:00",
        "订单付款时间_标准": datetime(2026, 8, 1, tzinfo=TZ),
        "商家备注": "",
        "物流单号": "W1",
        "购买数量": 1,
        "购买数量_标准": 1,
    }
    values.update(overrides)
    return values


def _table(tmp_path: Path, rows: list[dict[str, object]]) -> LoadedTable:
    path = tmp_path / "orders.xlsx"
    data = pd.DataFrame(rows)
    data.attrs["source_path"] = str(path)
    metadata = InputFileMetadata(
        role="订单表",
        path=path,
        sha256="a" * 64,
        size_bytes=1,
        rows=len(data),
        sheet="export",
    )
    return LoadedTable(data=data, metadata=metadata)


def test_cleaning_collects_all_matching_reasons(tmp_path: Path) -> None:
    table = _table(
        tmp_path,
        [
            _row(
                2,
                订单状态="交易关闭",
                物流单号="",
                商家备注="DS",
                买家应付货款="19.99",
                买家应付货款_分=1999,
            )
        ],
    )

    retained, deleted = apply_cleaning_rules(table)

    assert retained.empty
    assert deleted.iloc[0]["cleaning_reasons"] == (
        CleaningReason.CLOSED_WITHOUT_LOGISTICS.value,
        CleaningReason.NOTE_CONTAINS_D.value,
        CleaningReason.NOTE_CONTAINS_S.value,
    )


def test_cleaning_is_case_insensitive_contains_match_and_never_deletes_by_amount(
    tmp_path: Path,
) -> None:
    table = _table(
        tmp_path,
        [
            _row(2, 商家备注="s 张XY", 买家应付货款_分=2000),
            _row(3, 商家备注="补单d", 买家应付货款="0.01", 买家应付货款_分=1),
            _row(4, 商家备注="", 买家应付货款="0.01", 买家应付货款_分=1),
        ],
    )

    retained, deleted = apply_cleaning_rules(table)

    assert len(retained) == 1
    assert retained.iloc[0]["source_row_number"] == 4
    assert deleted.iloc[0]["cleaning_reasons"] == (CleaningReason.NOTE_CONTAINS_S.value,)
    assert deleted.iloc[1]["cleaning_reasons"] == (CleaningReason.NOTE_CONTAINS_D.value,)


def test_deleted_row_may_have_missing_payment_time(tmp_path: Path) -> None:
    table = _table(
        tmp_path,
        [_row(2, 商家备注="D", 订单付款时间=None, 订单付款时间_标准=None)],
    )

    result = partition_orders(table, _config(tmp_path))

    assert result.counts()[OrderPartition.DELETED_BY_RULE.value] == 1


def test_retained_row_requires_payment_time(tmp_path: Path) -> None:
    table = _table(
        tmp_path,
        [_row(2, 订单付款时间=None, 订单付款时间_标准=None)],
    )

    with pytest.raises(NormalizationError, match="付款时间不能为空"):
        partition_orders(table, _config(tmp_path))


def test_period_is_half_open_and_partitions_are_mutually_exclusive(tmp_path: Path) -> None:
    rows = [
        _row(2, 订单付款时间_标准=datetime(2026, 8, 1, tzinfo=TZ)),
        _row(
            3,
            订单付款时间_标准=datetime(2026, 8, 7, 23, 59, 59, 999999, tzinfo=TZ),
            订单状态="卖家已发货，等待买家确认",
        ),
        _row(4, 订单付款时间_标准=datetime(2026, 8, 8, tzinfo=TZ)),
        _row(5, 订单状态="交易关闭", 物流单号="W5"),
        _row(6, 商家编码=""),
        _row(7, 订单状态="等待买家付款"),
        _row(8, 商家备注="S"),
    ]

    result = partition_orders(_table(tmp_path, rows), _config(tmp_path))

    assert result.counts() == {
        "DELETED_BY_RULE": 1,
        "OUT_OF_PERIOD": 1,
        "NORMAL_CODED": 2,
        "CLOSED_SHIPPED_CODED": 1,
        "MISSING_MERCHANT_CODE": 1,
        "OTHER_STATUS": 1,
    }
    assert result.source_rows == len(rows)
    assert {issue.code for issue in result.issues} == {
        "ORDER_MERCHANT_CODE_MISSING",
        "ORDER_STATUS_UNRECOGNIZED",
    }


def test_price_difference_enters_normal_without_code(tmp_path: Path) -> None:
    table = _table(
        tmp_path,
        [
            _row(
                2,
                商品标题=" 补差价专用 ",
                商家编码="",
                买家应付货款="18.00",
                买家应付货款_分=1800,
                物流单号="0000",
            )
        ],
    )

    result = partition_orders(table, _config(tmp_path))

    assert len(result.normal) == 1
    assert result.missing_merchant_code.empty
    assert bool(result.normal.iloc[0]["是否补差价专用"])


def test_normal_order_requires_payment_and_successful_refund_amount(tmp_path: Path) -> None:
    missing_payment = _table(tmp_path, [_row(2, 买家应付货款=None, 买家应付货款_分=None)])
    with pytest.raises(NormalizationError, match="货款不能为空"):
        partition_orders(missing_payment, _config(tmp_path))

    missing_refund = _table(
        tmp_path,
        [_row(3, 退款状态="退款成功", 退款金额=None, 退款金额_分=None)],
    )
    with pytest.raises(NormalizationError, match="退款金额不能为空"):
        partition_orders(missing_refund, _config(tmp_path))


def test_closed_shipped_allows_missing_payment(tmp_path: Path) -> None:
    table = _table(
        tmp_path,
        [
            _row(
                2,
                订单状态="交易关闭",
                物流单号="W2",
                买家应付货款=None,
                买家应付货款_分=None,
            )
        ],
    )

    result = partition_orders(table, _config(tmp_path))

    assert len(result.closed_shipped) == 1
