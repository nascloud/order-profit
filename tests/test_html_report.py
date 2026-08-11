from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from order_profit.config import Platform, RunConfig
from order_profit.html_report import write_html
from order_profit.models import RunStatus


def test_html_escapes_business_text_and_embeds_safe_json(tmp_path: Path) -> None:
    config = RunConfig(
        orders=tmp_path / "orders.xlsx",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        platform=Platform.TMALL,
        output_dir=tmp_path / "output",
    )
    links = pd.DataFrame(
        [
            {
                "商品ID": "P1",
                "商品链接": "https://item.taobao.com/item.htm?id=P1",
                "商品标题": "<script>alert(1)</script>",
                "数据覆盖": "订单+推广",
                "核算状态": "完整",
                "盈利状态": "盈利",
                "正常订单行数": 1,
                "全部销售额_分": 10000,
                "全部有效退款_分": 0,
                "正常订单货品成本_分": 3000,
                "正常订单运费_分": 500,
                "平台扣点_分": 600,
                "综合税赋_分": 230,
                "关闭已发货损失_分": 0,
                "推广花费_分": 1000,
                "推广归因成交金额_分": 5000,
                "推广ROI": Decimal("5"),
                "含推广利润_分": 4670,
                "成本运费缺失行数": 0,
                "运营动作优先级": "中",
                "运营动作": "加投观察",
            }
        ]
    )
    summary = {
        "已核算销售额_分": 10000,
        "已核算有效退款_分": 0,
        "已核算货品成本_分": 3000,
        "已核算运费_分": 500,
        "已核算平台扣点_分": 600,
        "已核算综合税赋_分": 230,
        "关闭已发货损失_分": 0,
        "推广花费_分": 1000,
        "含推广净利润_分": 4670,
        "含推广净利率": Decimal("0.467"),
        "推广归因成交金额_分": 5000,
        "有效商品链接": 1,
        "订单+推广链接": 1,
        "仅订单链接": 0,
        "仅推广链接": 0,
    }
    result = SimpleNamespace(
        analysis=SimpleNamespace(summary=summary, links=links),
        reconciliation=SimpleNamespace(status=RunStatus.FINAL),
    )
    path = tmp_path / "report.html"

    write_html(result, config, path)
    page = path.read_text(encoding="utf-8")

    assert "<script>alert(1)</script>" not in page
    assert "\\u003cscript\\u003ealert(1)\\u003c/script\\u003e" in page
    assert "const DATA=" in page
    assert "搜索商品ID或标题" in page
    assert ".table-wrap{overflow:auto" in page
    assert "accountingCls" in page
