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


def test_supplement_matches_full_source_and_respects_overwrite(tmp_path: Path) -> None:
    orders = _loaded(
        tmp_path,
        "orders",
        [_order(2, 货品成本_分=500, 运费_分=None)],
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

    without_overwrite = apply_supplements(orders, supplements, overwrite_existing=False)
    assert without_overwrite.orders.data.iloc[0]["补充货品成本_分"] is None
    assert without_overwrite.orders.data.iloc[0]["补充运费_分"] == 20
    assert without_overwrite.audit.iloc[0]["成本处理原因"] == "目标已有值且未启用覆盖"

    with_overwrite = apply_supplements(orders, supplements, overwrite_existing=True)
    assert with_overwrite.orders.data.iloc[0]["补充货品成本_分"] == 100
    assert with_overwrite.orders.data.iloc[0]["补充运费_分"] == 20


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


def test_cost_and_freight_priority(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            _order(2, 补充货品成本_分=111, 补充运费_分=22, 物流单号="W2"),
            _order(3, 货品成本_分=300, 运费_分=30, 物流单号="W3"),
            _order(4, 商家编码="SKU4", 购买数量_标准=3),
        ]
    )
    costs = _loaded(
        tmp_path,
        "costs",
        [
            {"编码": "SKU2", "成本_分": 900, "运费_分": 90},
            {"编码": "SKU3", "成本_分": 900, "运费_分": 90},
            {"编码": "SKU4", "成本_分": 125, "运费_分": 45},
        ],
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [
            {"运单号": "W2", "总运费_分": 999},
            {"运单号": "W3", "总运费_分": 333},
        ],
    )

    result = resolve_costs_and_freight(
        _partitions(normal),
        costs=costs,
        freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    first, second, third = [row for _, row in result.normal.iterrows()]
    assert (first["核算成本_分"], first["成本来源"]) == (111, "人工补充")
    assert (first["核算运费_分"], first["运费来源"]) == (22, "人工补充")
    assert (second["核算成本_分"], second["成本来源"]) == (300, "订单表已有")
    assert (second["核算运费_分"], second["运费来源"]) == (333, "运费表实际运费")
    assert (third["核算成本_分"], third["成本来源"]) == (375, "成本编码表")
    assert (third["核算运费_分"], third["运费来源"]) == (45, "成本编码表标准运费")


def test_shared_actual_waybill_blocks_all_fallbacks(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            _order(2, 商家编码="A", 物流单号="SHARED", 运费_分=10),
            _order(3, 商家编码="B", 物流单号="SHARED", 运费_分=20),
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
        [{"运单号": "SHARED", "总运费_分": 50}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal),
        costs=costs,
        freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    assert result.normal["核算运费_分"].isna().all()
    assert set(result.normal["运费来源"]) == {"共享运单未核算"}
    assert result.normal["运费阻断回退"].all()
    assert [issue.code for issue in result.issues].count("FREIGHT_SHARED_WAYBILL") == 2


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
    assert (row["核算运费_分"], row["运费来源"]) == (0, "补差价专用业务规则")
    assert not result.issues


def test_price_difference_still_uses_actual_freight(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [_order(2, 商家编码="", 物流单号="REAL", 是否补差价专用=True)]
    )
    freight = _loaded(
        tmp_path,
        "freight",
        [{"运单号": "REAL", "总运费_分": 88}],
    )

    result = resolve_costs_and_freight(
        _partitions(normal),
        costs=None,
        freight=freight,
        supplement_audit=pd.DataFrame(),
    )

    assert result.normal.iloc[0]["核算运费_分"] == 88
    assert result.normal.iloc[0]["运费来源"] == "运费表实际运费"


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
