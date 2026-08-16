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
                "商品标题": "<img src=x onerror=document.body.dataset.pwned=1>",
                "数据覆盖": "订单+推广",
                "核算状态": "已核算",
                "盈利状态": "盈利",
                "产品名称": "产品一",
                "SABC等级": "S",
                "主订单数": 1,
                "购买数量": 1,
                "销售额_分": 10000,
                "刷单金额_分": 10000,
                "真实销售额_分": 0,
                "销售贡献率": Decimal("1"),
                "订单批次成功退款_分": 0,
                "退款率": Decimal("0"),
                "货品成本_分": 3000,
                "运费_分": 500,
                "刷单成本_分": 10000,
                "平台扣点_分": 600,
                "综合税赋_分": 230,
                "关闭已发货损失_分": 0,
                "推广花费_分": 1000,
                "推广归因成交金额_分": 5000,
                "推广投产比": Decimal("5"),
                "含推广经营贡献利润_分": 4670,
                "经营贡献利润率": Decimal("0.467"),
                "盈利贡献率": Decimal("1"),
                "成本运费缺失行数": 0,
                "运营动作优先级": "中",
                "运营动作": "加投观察",
            }
        ]
    )
    summary = {
        "已付款销售额_分": 10000,
        "订单批次成功退款金额_分": 0,
        "期间退款完结金额_分": 0,
        "净销售额_分": 10000,
        "刷单金额_分": 10000,
        "真实销售额_分": 0,
        "已核算销售额_分": 10000,
        "已核算订单批次成功退款_分": 0,
        "已核算货品成本_分": 3000,
        "已核算运费_分": 500,
        "已核算刷单成本_分": 10000,
        "已核算平台扣点_分": 600,
        "已核算综合税赋_分": 230,
        "关闭已发货损失_分": 0,
        "推广花费_分": 1000,
        "含推广经营贡献利润_分": 4670,
        "经营贡献利润率": Decimal("0.467"),
        "销售额核算覆盖率": Decimal("1"),
        "推广投产比": Decimal("5"),
        "推广归因成交金额_分": 5000,
        "有效商品链接": 1,
        "订单+推广链接": 1,
        "仅订单链接": 0,
        "仅推广链接": 0,
    }
    result = SimpleNamespace(
        analysis=SimpleNamespace(
            summary=summary,
            links=links,
            daily=pd.DataFrame(),
            products=pd.DataFrame(),
            sku=pd.DataFrame([{"商家编码": "SKU-1", "产品名称": "产品一", "购买数量": 1, "销售额_分": 10000}]),
        ),
        reconciliation=SimpleNamespace(status=RunStatus.FINAL),
    )
    path = tmp_path / "report.html"

    write_html(result, config, path)
    page = path.read_text(encoding="utf-8")

    assert "<img src=x" not in page
    assert "\\u003cimg src=x" in page
    assert "esc(r[c[1]]??'--')" in page
    assert "const DATA=" in page
    assert "搜索商品ID或标题" in page
    assert 'id="rankings"' in page
    assert "产品销售榜" in page
    assert "产品退款榜" in page
    assert "产品利润榜" in page
    assert "热销产品榜" in page
    assert "DATA.sku" in page
    assert "r['商家编码']||'无商家编码'" in page
    assert "销售占比 ${pct(paid?Number(r['销售额_分']||0)/paid:null)}" in page
    assert "r['经营贡献利润率状态']==='已核算'" in page
    assert "链接利润榜" in page
    assert "链接销售榜" in page
    assert "链接退款榜" in page
    assert "链接花费榜" in page
    assert "链接投产榜" in page
    assert "链接亏损预警" in page
    assert "r['核算状态']==='已核算'" in page
    assert "roiSpendFloor=Math.max(10000" in page
    assert "Number(r['推广花费_分']||0)>=roiSpendFloor" in page
    assert ".table-wrap{overflow:auto" in page
    assert "@media(max-width:700px)" in page
    assert "@page{size:A4 landscape" in page
    assert ".view[hidden]{display:block!important}" in page
    assert ".equation-scroll,.table-wrap{overflow:visible;max-height:none" in page
    assert ".equation,.profit-equation{width:100%;min-width:0;flex-direction:row!important}" in page
    assert "table{min-width:0" in page
    assert "含推广净利润" not in page
    assert "全部订单销售链" in page
    assert "已核算利润链" in page
    assert "刷单金额" in page
    assert "真实销售额" in page
    assert "term('真实销售额',realSales,'result'" in page
    assert "term('刷单成本',S['已核算刷单成本_分'],'cost'" in page
    assert "全部订单批次成功退款" in page
    assert "销售额核算覆盖率 ${pct(S['销售额核算覆盖率'])}" in page
    assert 'id="profitEquation"' in page
    assert "profit-equation" in page
    assert "term('关闭已发货损失'" in page
    assert "刷单成本同金额计入利润" in page
    assert "占已核算销售额 ${share(accountedRefund,accounted)}" in page
    assert "占净销售额 ${share(S['已核算平台扣点_分'],accountedNet)}" in page
    assert "占已核算净销售额 ${pct(accountedNet?S['推广花费_分']/accountedNet:null)}" in page
    assert ".equation:not(.profit-equation) .term{width:220px}" in page
