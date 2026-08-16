from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from order_profit.aggregate import PromotionResult, aggregate_promotion, build_analysis
from order_profit.config import Platform, RunConfig
from order_profit.inputs import LoadedTable
from order_profit.models import InputFileMetadata, RunStatus
from order_profit.profit import ProfitResult
from order_profit.reconcile import validate_reconciliation
from order_profit.rules import OrderPartitions

TZ = ZoneInfo("Asia/Shanghai")


def _config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        orders=tmp_path / "orders.xlsx",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        platform=Platform.TMALL,
        output_dir=tmp_path / "output",
    )


def _promotion_table(tmp_path: Path) -> LoadedTable:
    data = pd.DataFrame(
        [
            {
                "source_row_number": 2,
                "日期_标准": datetime(2026, 8, 1, tzinfo=TZ),
                "主体ID": "P1",
                "主体名称": "商品一",
                "展现量_标准": 100,
                "点击量_标准": 10,
                "花费_分": 1000,
                "总成交金额_分": 5000,
                "总成交笔数_标准": 2,
            },
            {
                "source_row_number": 3,
                "日期_标准": datetime(2026, 8, 7, 23, 59, 59, tzinfo=TZ),
                "主体ID": "P2",
                "主体名称": "商品二",
                "展现量_标准": 0,
                "点击量_标准": 0,
                "花费_分": 0,
                "总成交金额_分": 0,
                "总成交笔数_标准": 0,
            },
            {
                "source_row_number": 4,
                "日期_标准": datetime(2026, 8, 8, tzinfo=TZ),
                "主体ID": "P3",
                "主体名称": "超期",
                "展现量_标准": 1,
                "点击量_标准": 1,
                "花费_分": 100,
                "总成交金额_分": 100,
                "总成交笔数_标准": 1,
            },
        ]
    )
    return LoadedTable(
        data=data,
        metadata=InputFileMetadata(
            role="推广报表",
            path=tmp_path / "promotion.csv",
            sha256="a" * 64,
            size_bytes=1,
            rows=3,
            encoding="utf-8-sig",
        ),
    )


def _profit() -> ProfitResult:
    normal = pd.DataFrame(
        [
            {
                "source_row_number": 2,
                "主订单编号": "O1",
                "商品ID": "P1",
                "商品标题": "<script>alert(1)</script>",
                "订单付款时间_标准": datetime(2026, 8, 1, tzinfo=TZ),
                "购买数量_标准": 1,
                "实收金额_分": 10000,
                "有效退款_分": 1000,
                "核算成本_分": 3000,
                "核算运费_分": 500,
                "平台扣点_分": 540,
                "综合税赋_分": 207,
                "刷单成本_分": 10000,
                "正常订单利润_分": 4753,
                "核算状态": "已核算",
                "商家编码": "SKU1",
                "cleaning_reasons": ("商家备注包含字母D/d",),
            }
        ]
    )
    closed = pd.DataFrame(
        [
            {
                "source_row_number": 3,
                "主订单编号": "O2",
                "商品ID": "P1",
                "商品标题": "订单标题",
                "订单付款时间_标准": datetime(2026, 8, 2, tzinfo=TZ),
                "购买数量_标准": 1,
                "核算成本_分": 1000,
                "核算运费_分": 200,
                "关闭已发货损失_分": 1200,
                "核算状态": "已核算",
                "商家编码": "SKU1",
                "cleaning_reasons": (),
            }
        ]
    )
    return ProfitResult(normal, closed, pd.DataFrame())


def test_promotion_period_and_zero_denominator(tmp_path: Path) -> None:
    result = aggregate_promotion(_promotion_table(tmp_path), _config(tmp_path))

    assert len(result.detail) == 2
    assert len(result.out_of_period) == 1
    assert int(result.daily["推广花费_分"].sum()) == 1000
    p1 = result.products[result.products["主体ID"] == "P1"].iloc[0]
    assert p1["推广投产比"] == Decimal("5")
    p2 = result.products[result.products["主体ID"] == "P2"].iloc[0]
    assert "推广投产比" in p2["零分母状态"]


def test_link_union_summary_and_reconciliation(tmp_path: Path) -> None:
    promotion = aggregate_promotion(_promotion_table(tmp_path), _config(tmp_path))
    profit = _profit()
    analysis = build_analysis(profit, promotion, _config(tmp_path))

    assert set(analysis.links["商品ID"]) == {"P1", "P2"}
    assert analysis.summary["订单+推广链接"] == 1
    assert analysis.summary["仅推广链接"] == 1
    assert analysis.summary["已核算销售额_分"] == 10000
    assert analysis.summary["刷单金额_分"] == 10000
    assert analysis.summary["已核算刷单成本_分"] == 10000
    assert analysis.summary["真实销售额_分"] == -1000
    assert analysis.links.loc[analysis.links["商品ID"] == "P1", "刷单金额_分"].iloc[0] == 10000
    assert analysis.links.loc[analysis.links["商品ID"] == "P1", "刷单成本_分"].iloc[0] == 10000
    assert analysis.links.loc[analysis.links["商品ID"] == "P1", "真实销售额_分"].iloc[0] == -1000
    assert analysis.daily.iloc[0]["刷单金额_分"] == 10000
    assert analysis.daily.iloc[0]["真实销售额_分"] == -1000
    assert analysis.summary["含推广经营贡献利润_分"] == 2553
    assert analysis.summary["退款订单率"] == Decimal("0.5")
    assert analysis.summary["付款后关闭率"] == Decimal("0.5")
    assert analysis.summary["关闭已发货率"] == Decimal("0.5")
    assert analysis.daily.iloc[0]["成本率"] == Decimal("0")
    assert analysis.daily.iloc[0]["平台费率"] == Decimal("0.06")
    assert analysis.daily.iloc[0]["税费率"] == Decimal("0.023")
    assert analysis.daily.iloc[0]["推广费率"] == Decimal(1000) / Decimal(9000)
    assert analysis.summary["经营贡献利润率"] == Decimal(2553) / Decimal(9000)
    assert analysis.products.loc[analysis.products["产品名称"] == "未归类", "商品链接数"].iloc[0] == 2

    empty = profit.normal.iloc[0:0].copy()
    partitions = OrderPartitions(
        deleted=empty.copy(),
        out_of_period=empty.copy(),
        normal=profit.normal,
        closed_shipped=profit.closed_shipped,
        missing_merchant_code=empty.copy(),
        other_status=empty.copy(),
    )
    result = validate_reconciliation(
        analysis,
        partitions,
        source_order_rows=2,
    )
    assert result.status is RunStatus.FINAL
    assert all(check.passed for check in result.checks)


def test_sabc_and_multi_product_promotion_allocation_are_deterministic(tmp_path: Path) -> None:
    def row(number: int, link: str, product: str, sales: int, profit: int, status: str = "已核算") -> dict[str, object]:
        return {
            "source_row_number": number, "主订单编号": f"O{number}", "商品ID": link,
            "商品标题": link, "订单付款时间_标准": datetime(2026, 8, 1, tzinfo=TZ),
            "购买数量_标准": 1, "实收金额_分": sales, "有效退款_分": 0,
            "核算成本_分": 0 if status == "已核算" else None, "核算运费_分": 0,
            "平台扣点_分": 0, "综合税赋_分": 0, "正常订单利润_分": profit if status == "已核算" else None,
            "核算状态": status, "商家编码": f"SKU{number}", "产品名称": product,
        }

    normal = pd.DataFrame([
        row(2, "P1", "产品甲", 10000, 6000), row(3, "P1", "产品乙", 5000, 0),
        row(4, "P2", "产品甲", 3000, 3000), row(5, "P3", "产品甲", 1000, 1000),
        row(6, "P4", "产品甲", 1000, -100), row(7, "P5", "产品甲", 1000, 0, "成本或运费缺失"),
    ])
    profit = ProfitResult(normal, normal.iloc[0:0].copy(), pd.DataFrame())
    promotion_products = pd.DataFrame([{
        "主体ID": "P1", "主体名称": "P1", "推广花费_分": 101,
        "推广归因成交金额_分": 1001, "推广成交笔数": 2,
        "推广展现量": 0, "推广点击量": 0, "推广投产比": Decimal("9.910891"), "点击率": Decimal("0"),
    }])
    promotion = PromotionResult(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), promotion_products)

    analysis = build_analysis(profit, promotion, _config(tmp_path))

    assert dict(zip(analysis.links["商品ID"], analysis.links["SABC等级"], strict=True)) == {
        "P1": "S", "P2": "A", "P3": "B", "P4": "C", "P5": "待核算",
    }
    allocated = analysis.products.set_index("产品名称")
    assert int(allocated["推广花费_分"].sum()) == 101
    assert int(allocated["推广归因成交金额_分"].sum()) == 1001
    assert allocated.at["产品甲", "推广花费_分"] == 68
    assert allocated.at["产品乙", "推广花费_分"] == 33
    assert allocated.at["产品甲", "经营贡献利润率状态"] == "待核算"
    assert pd.isna(allocated.at["产品甲", "经营贡献利润率"])
    assert allocated.at["产品乙", "经营贡献利润率"] == Decimal("-0.0066")
    assert analysis.summary["盈利链接数"] == 3
    assert analysis.summary["亏损链接数"] == 1
