from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from order_profit.config import Platform, RunConfig
from order_profit.costs import CostResolutionResult
from order_profit.profit import calculate_order_profit


def _config(tmp_path: Path, platform: Platform = Platform.TMALL) -> RunConfig:
    return RunConfig(
        orders=tmp_path / "orders.xlsx",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        platform=platform,
        output_dir=tmp_path / "output",
    )


def test_normal_profit_includes_refund_platform_fee_and_tax(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            {
                "source_sheet": "export",
                "source_row_number": 2,
                "主订单编号": "O1",
                "商品ID": "P1",
                "退款状态": "退款成功",
                "退款金额_分": 1000,
                "买家应付货款_分": 10000,
                "核算成本_分": 3000,
                "核算运费_分": 500,
            }
        ]
    )
    costs = CostResolutionResult(
        normal=normal,
        closed_shipped=normal.iloc[0:0].copy(),
        supplement_audit=pd.DataFrame(),
    )

    result = calculate_order_profit(costs, _config(tmp_path))
    row = result.normal.iloc[0]

    assert row["费用计费基数_分"] == 9000
    assert row["平台扣点_分"] == 540
    assert row["综合税赋_分"] == 207
    assert row["正常订单利润_分"] == 4753
    assert row["利润率"] == Decimal(4753) / Decimal(9000)


def test_missing_cost_keeps_profit_empty_but_still_calculates_fees(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            {
                "source_sheet": "export",
                "source_row_number": 2,
                "主订单编号": "O1",
                "商品ID": "P1",
                "退款状态": "无退款",
                "退款金额_分": None,
                "买家应付货款_分": 10000,
                "核算成本_分": None,
                "核算运费_分": 500,
            }
        ]
    )
    costs = CostResolutionResult(
        normal=normal,
        closed_shipped=normal.iloc[0:0].copy(),
        supplement_audit=pd.DataFrame(),
    )

    row = calculate_order_profit(costs, _config(tmp_path, Platform.TAOBAO)).normal.iloc[0]

    assert row["平台扣点_分"] == 60
    assert row["综合税赋_分"] == 230
    assert pd.isna(row["正常订单利润_分"])
    assert row["核算状态"] == "成本或运费缺失"


def test_brush_order_amount_becomes_brush_cost_and_not_profit(tmp_path: Path) -> None:
    normal = pd.DataFrame(
        [
            {
                "source_sheet": "export",
                "source_row_number": 2,
                "主订单编号": "O1",
                "商品ID": "P1",
                "退款状态": "无退款",
                "退款金额_分": None,
                "买家应付货款_分": 10000,
                "核算成本_分": 3000,
                "核算运费_分": 500,
                "cleaning_reasons": ("商家备注包含字母D/d",),
            }
        ]
    )
    costs = CostResolutionResult(
        normal=normal,
        closed_shipped=normal.iloc[0:0].copy(),
        supplement_audit=pd.DataFrame(),
    )

    row = calculate_order_profit(costs, _config(tmp_path)).normal.iloc[0]

    assert row["平台扣点_分"] == 600
    assert row["综合税赋_分"] == 230
    assert row["刷单成本_分"] == 10000
    assert row["正常订单利润_分"] == -830


def test_closed_loss_is_positive_and_profit_is_negative(tmp_path: Path) -> None:
    closed = pd.DataFrame(
        [{"核算成本_分": 3000, "核算运费_分": 500}]
    )
    costs = CostResolutionResult(
        normal=pd.DataFrame(
            columns=[
                "退款状态",
                "退款金额_分",
                "买家应付货款_分",
                "核算成本_分",
                "核算运费_分",
            ]
        ),
        closed_shipped=closed,
        supplement_audit=pd.DataFrame(),
    )

    row = calculate_order_profit(costs, _config(tmp_path)).closed_shipped.iloc[0]

    assert row["关闭已发货损失_分"] == 3500
    assert row["关闭明细利润_分"] == -3500
