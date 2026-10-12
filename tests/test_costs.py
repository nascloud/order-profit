from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from order_profit.costs import apply_supplements, resolve_costs_and_freight
from order_profit.errors import InputContractError
from order_profit.inputs import LoadedTable
from order_profit.models import InputFileMetadata
from order_profit.rules import OrderPartitions


def _metadata(tmp_path: Path, role: str, rows: int) -> InputFileMetadata:
    return InputFileMetadata(
        role=role,
        path=tmp_path / f"{role}.xlsx",
        sha256="a" * 64,
        size_bytes=1,
        rows=rows,
        sheet="Sheet1",
    )


def _loaded(tmp_path: Path, role: str, rows: list[dict[str, object]]) -> LoadedTable:
    data = pd.DataFrame(rows)
    data.attrs["source_path"] = str(tmp_path / f"{role}.xlsx")
    return LoadedTable(data=data, metadata=_metadata(tmp_path, role, len(data)))


def _order(number: int, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_file_id": "a" * 16,
        "source_sheet": "export",
        "source_row_number": number,
        "source_row_id": f"order:{number}",
        "主订单编号": f"O{number}",
        "商品ID": f"P{number}",
        "商家编码": f"SKU{number}",
        "购买数量_标准": 1,
        "物流单号": "",
        "货品成本_分": None,
        "运费_分": None,
        "补充货品成本_分": None,
        "补充运费_分": None,
    }
    row.update(overrides)
    return row


def _supplement(number: int, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_sheet": "Sheet1",
        "source_row_number": number,
        "主订单编号": f"O{number}",
        "商品ID": f"P{number}",
        "商家编码": f"SKU{number}",
        "货品成本_分": 100,
        "运费_分": 20,
        "补充状态": "已确认",
    }
    row.update(overrides)
    return row


def _partitions(normal: pd.DataFrame, closed: pd.DataFrame | None = None) -> OrderPartitions:
    empty = normal.iloc[0:0].copy()
    return OrderPartitions(
        deleted=empty.copy(),
        out_of_period=empty.copy(),
        normal=normal,
        closed_shipped=(closed if closed is not None else empty.copy()),
        missing_merchant_code=empty.copy(),
        other_status=empty.copy(),
    )


def test_supplement_matches_full_source_without_order_amount_columns(tmp_path: Path) -> None:
    orders = _loaded(
        tmp_path,
        "orders",
        [_order(2)],
    )
    supplements = _loaded(
        tmp_path,
        "supplements",
        [
            _supplement(
                9,
                主订单编号="O2",
                商品ID="P2",
                商家编码="SKU2",
                货品成本_分=100,
                运费_分=20,
            )
        ],
    )

    result = apply_supplements(orders, supplements, overwrite_existing=False)
    assert result.orders.data.iloc[0]["补充货品成本_分"] == 100
    assert result.orders.data.iloc[0]["补充运费_分"] == 20
    assert bool(result.audit.iloc[0]["成本已应用"])
    assert bool(result.audit.iloc[0]["运费已应用"])


def test_generated_missing_freight_can_override_blocking_source_value(
    tmp_path: Path,
) -> None:
    orders = _loaded(
        tmp_path,
        "orders",
        [_order(2, 运费_分=0)],
    )
    supplements = _loaded(
        tmp_path,
        "supplements",
        [
            _supplement(
                9,
                主订单编号="O2",
                商品ID="P2",
                商家编码="SKU2",
                货品成本_分=None,
                运费_分=1025,
                缺失项目="运费",
            )
        ],
    )

    result = apply_supplements(orders, supplements, overwrite_existing=False)

    assert result.orders.data.iloc[0]["补充运费_分"] == 1025
    assert bool(result.audit.iloc[0]["运费已应用"])


def test_inactive_supplement_matches_but_does_not_apply(tmp_path: Path) -> None:
    orders = _loaded(tmp_path, "orders", [_order(2)])
    supplements = _loaded(
        tmp_path,
        "supplements",
        [_supplement(9, 主订单编号="O2", 商品ID="P2", 商家编码="SKU2", 补充状态="草稿")],
    )

    result = apply_supplements(orders, supplements, overwrite_existing=False)

    assert result.orders.data.iloc[0]["补充货品成本_分"] is None
    assert result.audit.iloc[0]["成本处理原因"] == "状态不生效"


def test_supplement_rejects_missing_or_non_unique_target(tmp_path: Path) -> None:
    supplement = _loaded(tmp_path, "supplements", [_supplement(9)])
    with pytest.raises(InputContractError, match="找不到"):
        apply_supplements(
            _loaded(tmp_path, "orders", [_order(2)]),
            supplement,
            overwrite_existing=False,
        )

    duplicate_orders = _loaded(
        tmp_path,
        "orders",
        [
            _order(9),
            _order(10, 主订单编号="O9", 商品ID="P9", 商家编码="SKU9"),
        ],
    )
    with pytest.raises(InputContractError, match="多条"):
        apply_supplements(duplicate_orders, supplement, overwrite_existing=False)


def test_manual_supplement_is_only_used_when_reference_tables_do_not_resolve(
    tmp_path: Path,
) -> None:
    normal = pd.DataFrame(
        [
            _order(2, 补充货品成本_分=111, 补充运费_分=22, 物流单号="W2"),
            _order(3, 补充货品成本_分=333, 补充运费_分=44, 物流单号="MISSING"),
            _order(4, 商家编码="SKU4", 购买数量_标准=3),
        ]
    )
    costs = _loaded(
        tmp_path,
        "costs",
        [
            {"编码": "SKU2", "成本_分": 900, "运费_分": 90},
            {"编码": "SKU4", "成本_分": 125, "运费_分": 45},
        ],
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [
            {"运单号": "W2", "主订单编号": "O2", "总运费_分": 999},
        ],
    )

    result = resolve_costs_and_freight(
        _partitions(normal),
        costs=costs,
        freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    first, second, third = [row for _, row in result.normal.iterrows()]
    assert (first["核算成本_分"], first["成本来源"]) == (900, "成本编码表")
    assert first["核算运费_分"] == 999
    assert (second["核算成本_分"], second["成本来源"]) == (333, "人工补充")
    assert second["核算运费_分"] == 44
    assert (third["核算成本_分"], third["成本来源"]) == (375, "成本编码表")
    assert third["核算运费_分"] == 45
    assert int(result.normal["核算运费_分"].sum()) == 1088


def test_brush_order_without_code_resolves_zero_cost_and_freight(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [_order(2, 商家编码="", 订单状态="交易成功", 商家备注="D")]
    )

    result = resolve_costs_and_freight(
        _partitions(normal),
        costs=None,
        freight=None,
        supplement_audit=pd.DataFrame(),
    )
    row = result.normal.iloc[0]

    assert row["核算成本_分"] == 0
    assert row["成本来源"] == "刷单业务规则"
    assert row["核算运费_分"] == 0
    assert result.missing_cost_rows == 0
    assert result.missing_freight_rows == 0
    assert not result.issues


@pytest.mark.parametrize("marker", ["D", "d", "S", "s"])
def test_same_order_brush_row_does_not_take_ordinary_row_freight(
    tmp_path: Path, marker: str,
) -> None:
    normal = pd.DataFrame(
        [
            _order(2, 主订单编号="SAME", 订单状态="交易成功", 商家备注=marker),
            _order(3, 主订单编号="SAME", 订单状态="交易成功", 商家备注="",
                   补充货品成本_分=100),
        ]
    )
    freight = _loaded(
        tmp_path, "freight",
        [{"运单号": "MOTHER", "主订单编号": "SAME", "总运费_分": 1000}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal), costs=None, freight=freight, supplement_audit=pd.DataFrame()
    )

    assert result.normal["核算运费_分"].tolist() == [0, 1000]
    assert int(result.normal["核算运费_分"].sum()) == 1000
    assert result.normal["核算成本_分"].tolist() == [0, 100]
    assert not result.issues


def test_same_order_brush_normal_row_leaves_actual_freight_to_closed_row(
    tmp_path: Path,
) -> None:
    normal = pd.DataFrame(
        [_order(2, 主订单编号="SAME", 订单状态="交易成功", 商家备注="D")]
    )
    closed = pd.DataFrame(
        [_order(3, 主订单编号="SAME", 订单状态="交易关闭", 商家备注="D",
                物流单号="CLOSED", 补充货品成本_分=100)]
    )
    freight = _loaded(
        tmp_path, "freight",
        [{"运单号": "MOTHER", "主订单编号": "SAME", "总运费_分": 1000}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal, closed), costs=None, freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    assert result.normal["核算运费_分"].tolist() == [0]
    assert result.closed_shipped["核算运费_分"].tolist() == [1000]
    assert result.closed_shipped["核算成本_分"].tolist() == [100]
    assert not result.issues


def test_same_order_only_brush_rows_ignore_actual_freight(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            _order(2, 主订单编号="SAME", 订单状态="交易成功", 商家备注="D"),
            _order(3, 主订单编号="SAME", 订单状态="交易成功", 商家备注="S"),
        ]
    )
    freight = _loaded(
        tmp_path, "freight",
        [{"运单号": "MOTHER", "主订单编号": "SAME", "总运费_分": 1000}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal), costs=None, freight=freight, supplement_audit=pd.DataFrame()
    )

    assert result.normal["核算运费_分"].tolist() == [0, 0]
    assert result.normal["核算成本_分"].tolist() == [0, 0]
    assert result.missing_freight_rows == 0
    assert not result.issues


def test_same_order_normal_rows_take_freight_instead_of_closed_rows(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            _order(
                2,
                主订单编号="SAME",
                商家编码="A",
                物流单号="NORMAL-WAYBILL",
                购买数量_标准=1,
            )
        ]
    )
    closed = pd.DataFrame(
        [
            _order(
                3,
                主订单编号="SAME",
                商家编码="B",
                物流单号="CLOSED-WAYBILL",
                购买数量_标准=3,
            )
        ]
    )
    costs = _loaded(
        tmp_path,
        "costs",
        [
            {"编码": "A", "成本_分": 100, "运费_分": 30},
            {"编码": "B", "成本_分": 200, "运费_分": 40},
        ],
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [{"运单号": "FREIGHT-WAYBILL", "主订单编号": "SAME", "总运费_分": 1201}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal, closed),
        costs=costs,
        freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    assert result.normal.iloc[0]["核算运费_分"] == 1201
    assert result.closed_shipped.iloc[0]["核算运费_分"] == 0
    assert (
        int(result.normal["核算运费_分"].sum())
        + int(result.closed_shipped["核算运费_分"].sum())
    ) == 1201
    assert not result.issues


def test_same_order_multiple_normal_rows_split_by_quantity(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            _order(2, 主订单编号="SAME", 商家编码="A", 物流单号="WAYBILL-A", 购买数量_标准=1),
            _order(3, 主订单编号="SAME", 商家编码="B", 物流单号="WAYBILL-B", 购买数量_标准=3),
        ]
    )
    costs = _loaded(
        tmp_path,
        "costs",
        [
            {"编码": "A", "成本_分": 100, "运费_分": 30},
            {"编码": "B", "成本_分": 200, "运费_分": 40},
        ],
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [{"运单号": "FREIGHT-WAYBILL", "主订单编号": "SAME", "总运费_分": 1201}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal), costs=costs, freight=freight, supplement_audit=pd.DataFrame()
    )

    assert result.normal["核算运费_分"].tolist() == [300, 901]
    assert int(result.normal["核算运费_分"].sum()) == 1201


def test_different_orders_with_same_logistics_match_their_own_freight(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            _order(
                2,
                主订单编号="ORDER-A",
                商家编码="A",
                物流单号="SHARED",
                购买数量_标准=1,
                运费_分=10,
            ),
            _order(
                3,
                主订单编号="ORDER-B",
                商家编码="B",
                物流单号="SHARED",
                购买数量_标准=3,
                运费_分=20,
            ),
        ]
    )
    costs = _loaded(
        tmp_path,
        "costs",
        [
            {"编码": "A", "成本_分": 100, "运费_分": 30},
            {"编码": "B", "成本_分": 200, "运费_分": 40},
        ],
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [
            {"运单号": "WAYBILL-A", "主订单编号": "ORDER-A", "总运费_分": 137},
            {"运单号": "WAYBILL-B", "主订单编号": "ORDER-B", "总运费_分": 263},
        ],
    )

    result = resolve_costs_and_freight(
        _partitions(normal),
        costs=costs,
        freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    assert result.normal["核算运费_分"].tolist() == [137, 263]
    assert not result.issues
    assert int(result.normal["核算运费_分"].sum()) == 400


@pytest.mark.parametrize("logistics_number", ["CHILD", "UNLISTED", ""])
def test_order_freight_sums_zero_child_and_multiple_charged_waybills(
    tmp_path: Path, logistics_number: str
) -> None:
    normal = pd.DataFrame(
        [_order(2, 物流单号=logistics_number, 补充运费_分=77)]
    )
    costs = _loaded(
        tmp_path,
        "costs",
        [{"编码": "SKU2", "成本_分": 100, "运费_分": 50}],
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [
            {"运单号": "CHILD", "主订单编号": "O2", "总运费_分": 0},
            {"运单号": "MOTHER", "主订单编号": "O2", "总运费_分": 1201},
            {"运单号": "SECOND-CHARGED", "主订单编号": "O2", "总运费_分": 307},
            {"运单号": "OTHER-ORDER", "主订单编号": "O9", "总运费_分": 9999},
        ],
    )

    result = resolve_costs_and_freight(
        _partitions(normal), costs=costs, freight=freight, supplement_audit=pd.DataFrame()
    )

    assert result.normal["核算运费_分"].tolist() == [1508]
    assert int(result.normal["核算运费_分"].sum()) == 1508
    assert result.missing_freight_rows == 0
    assert not result.issues


@pytest.mark.parametrize("standard_freight", [90, None])
def test_all_zero_actual_freight_does_not_fall_back(
    tmp_path: Path, standard_freight: int | None
) -> None:
    normal = pd.DataFrame(
        [_order(2, 物流单号="CHILD", 补充货品成本_分=100, 补充运费_分=77)]
    )
    costs = (
        _loaded(
            tmp_path,
            "costs",
            [{"编码": "SKU2", "成本_分": 100, "运费_分": standard_freight}],
        )
        if standard_freight is not None
        else None
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [
            {"运单号": "CHILD", "主订单编号": "O2", "总运费_分": 0},
            {"运单号": "MOTHER", "主订单编号": "O2", "总运费_分": 0},
        ],
    )

    result = resolve_costs_and_freight(
        _partitions(normal), costs=costs, freight=freight, supplement_audit=pd.DataFrame()
    )

    assert result.normal["核算运费_分"].tolist() == [0]
    assert int(result.normal["核算运费_分"].sum()) == 0
    assert result.missing_freight_rows == 0
    assert not result.issues


def test_unmatched_order_uses_standard_then_manual_even_with_matching_waybill(
    tmp_path: Path,
) -> None:
    normal = pd.DataFrame(
        [
            _order(2, 物流单号="SHARED", 购买数量_标准=3, 补充运费_分=77),
            _order(
                3,
                物流单号="SHARED",
                购买数量_标准=2,
                补充货品成本_分=100,
                补充运费_分=88,
            ),
        ]
    )
    costs = _loaded(
        tmp_path,
        "costs",
        [{"编码": "SKU2", "成本_分": 100, "运费_分": 50}],
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [{"运单号": "SHARED", "主订单编号": "OTHER-ORDER", "总运费_分": 1201}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal), costs=costs, freight=freight, supplement_audit=pd.DataFrame()
    )

    assert result.normal["核算运费_分"].tolist() == [50, 88]
    assert int(result.normal["核算运费_分"].sum()) == 138
    assert result.missing_freight_rows == 0
    assert not result.issues


@pytest.mark.parametrize(
    ("quantities", "expected"),
    [
        ((1, 3), [300, 901]),
        ((1, 1), [600, 601]),
    ],
)
def test_order_with_only_closed_rows_splits_freight_by_quantity_and_source_row(
    tmp_path: Path, quantities: tuple[int, int], expected: list[int]
) -> None:
    closed = pd.DataFrame(
        [
            _order(
                3,
                主订单编号="SAME",
                物流单号="CLOSED-A",
                购买数量_标准=quantities[0],
            ),
            _order(
                2,
                主订单编号="SAME",
                物流单号="CLOSED-B",
                购买数量_标准=quantities[1],
            ),
        ]
    )
    costs = _loaded(
        tmp_path,
        "costs",
        [
            {"编码": "SKU2", "成本_分": 100, "运费_分": 30},
            {"编码": "SKU3", "成本_分": 200, "运费_分": 40},
        ],
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [{"运单号": "FREIGHT-WAYBILL", "主订单编号": "SAME", "总运费_分": 1201}],
    )

    result = resolve_costs_and_freight(
        _partitions(closed.iloc[0:0].copy(), closed),
        costs=costs,
        freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    assert result.normal.empty
    assert result.closed_shipped["核算运费_分"].tolist() == expected
    assert int(result.closed_shipped["核算运费_分"].sum()) == 1201
    assert result.missing_freight_rows == 0
    assert not result.issues


def test_price_difference_has_known_zero_cost_and_freight_without_actual_match(
    tmp_path: Path,
) -> None:
    normal = pd.DataFrame(
        [
            _order(
                2,
                商家编码="",
                物流单号="0000",
                是否补差价专用=True,
                货品成本_分=None,
                运费_分=None,
            )
        ]
    )

    result = resolve_costs_and_freight(
        _partitions(normal),
        costs=None,
        freight=None,
        supplement_audit=pd.DataFrame(),
    )

    row = result.normal.iloc[0]
    assert (row["核算成本_分"], row["成本来源"]) == (0, "补差价专用业务规则")
    assert row["核算运费_分"] == 0
    assert not result.issues


def test_price_difference_still_uses_actual_freight(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [_order(2, 商家编码="", 物流单号="REAL", 是否补差价专用=True)]
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [{"运单号": "REAL", "主订单编号": "O2", "总运费_分": 88}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal),
        costs=None,
        freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    assert result.normal.iloc[0]["核算运费_分"] == 88
    assert int(result.normal["核算运费_分"].sum()) == 88


def test_supplement_audit_records_non_period_partition(tmp_path: Path) -> None:
    normal = pd.DataFrame([_order(2)])
    deleted = pd.DataFrame([_order(8)])
    empty = normal.iloc[0:0].copy()
    partitions = OrderPartitions(
        deleted=deleted,
        out_of_period=empty.copy(),
        normal=normal,
        closed_shipped=empty.copy(),
        missing_merchant_code=empty.copy(),
        other_status=empty.copy(),
    )
    audit = pd.DataFrame([{"匹配订单源行": 8}])

    result = resolve_costs_and_freight(
        partitions,
        costs=None,
        freight=None,
        supplement_audit=audit,
    )

    assert result.supplement_audit.iloc[0]["匹配订单分区"] == "DELETED_BY_RULE"
