from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from playwright.sync_api import Browser, Page, expect, sync_playwright

from order_profit.config import Platform, RunConfig
from order_profit.html_report import write_html
from order_profit.models import RunStatus


@pytest.fixture(scope="module")
def html_browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def html_page(html_browser: Browser) -> Iterator[Page]:
    page = html_browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda message: errors.append(message.text)
            if message.type in ("error", "warning") else None)
    yield page
    expect(page.locator("#reportError")).to_be_hidden()
    page.close()
    assert not errors


def report(
    tmp_path: Path,
    *,
    daily: list[dict] | None = None,
    empty: bool = False,
    status: RunStatus = RunStatus.FINAL,
    summary: dict | None = None,
    links: list[dict] | None = None,
    products: list[dict] | None = None,
) -> Path:
    base = {
        "产品名称": "产品一", "商品ID": "P1", "商品标题": "产品一长标题",
        "SABC等级": "S", "数据覆盖": "订单+推广", "核算状态": "已核算",
        "盈利状态": "盈利", "销售额_分": 10000, "真实销售额_分": 10000,
        "退款率": Decimal("0.05"), "推广花费_分": 1000,
        "含推广经营贡献利润_分": 4670, "经营贡献利润率": Decimal("0.467"),
        "货品成本_分": 3000, "运费_分": 500, "平台扣点_分": 600,
        "综合税赋_分": 230, "关闭已发货损失_分": 0, "刷单成本_分": 1000,
        "订单批次成功退款_分": 0, "运营动作": "加投观察",
        "经营贡献利润率状态": "已核算", "商品链接": "javascript:alert(1)",
    }
    second = {**base, "商品ID": "P2", "产品名称": "产品二", "销售额_分": 900,
              "商品标题": "<img src=x onerror=document.body.dataset.pwned=1></script>",
              "含推广经营贡献利润_分": -300, "盈利状态": "亏损"}
    third = {**base, "商品ID": "P3", "产品名称": "待核算产品",
             "核算状态": "成本或运费缺失", "经营贡献利润率状态": "待核算"}
    result = SimpleNamespace(
        analysis=SimpleNamespace(
            summary=summary if summary is not None else {
                "真实销售额_分": 10000, "已付款销售额_分": 10000,
                "已核算销售额_分": 10000, "已核算订单批次成功退款_分": 0,
                "已核算货品成本_分": 3000, "已核算运费_分": 500,
                "已核算刷单成本_分": 1000, "已核算平台扣点_分": 600,
                "已核算综合税赋_分": 230, "关闭已发货损失_分": 0,
                "推广花费_分": 0, "含推广经营贡献利润_分": 4670,
                "经营贡献利润率": Decimal("0.467"), "销售额核算覆盖率": Decimal("1"),
            },
            daily=pd.DataFrame(daily or []),
            links=pd.DataFrame(
                links if links is not None else [] if empty else [base, second, third]
            ),
            products=pd.DataFrame(
                products if products is not None else [] if empty else [base, second, third]
            ),
            sku=pd.DataFrame(),
        ),
        reconciliation=SimpleNamespace(status=status),
    )
    config = RunConfig(orders=tmp_path / "orders.xlsx", start_date=date(2026, 8, 1),
                       end_date=date(2026, 8, 7), platform=Platform.TMALL,
                       output_dir=tmp_path / "output")
    path = tmp_path / "report.html"
    write_html(result, config, path)
    return path


def open_view(page: Page, view: str) -> None:
    page.locator(f'nav [data-view="{view}"]').click()


def test_libraries_are_embedded_and_offline(tmp_path: Path, html_page: Page) -> None:
    requests = []
    html_page.on("request", lambda request: requests.append(request.url))
    html_page.goto(report(tmp_path).as_uri())
    for view in ("daily", "products", "links"):
        open_view(html_page, view)
    assert not [url for url in requests if url.startswith(("http:", "https:"))]
    assert html_page.evaluate("typeof echarts.init") == "function"
    assert html_page.evaluate("typeof Tabulator") == "function"
    expect(html_page.locator("#keyMetrics")).to_contain_text("¥46.70")
    expect(html_page.locator("#libraryLicenses")).to_contain_text("Apache")


def test_column_presets_custom_columns_filters_sort_and_details(
    tmp_path: Path, html_page: Page
) -> None:
    html_page.goto(report(tmp_path).as_uri())
    open_view(html_page, "links")
    grid = html_page.locator("#linksGrid")
    expect(grid.locator('.tabulator-col[tabulator-field="货品成本_分"]')).to_be_hidden()
    html_page.get_by_label("商品搜索", exact=True).fill("P1")
    expect(html_page.locator("#linkCount")).to_have_text("匹配 1 / 3 个链接")
    html_page.locator('#links [data-preset="cost"]').click()
    expect(grid.locator('.tabulator-col[tabulator-field="货品成本_分"]')).to_be_visible()
    expect(html_page.get_by_label("商品搜索", exact=True)).to_have_value("P1")
    html_page.locator('#links [data-preset="all"]').click()
    expect(grid.locator('.tabulator-col[tabulator-field="商品标题"]')).to_be_visible()
    html_page.locator('#links summary').click()
    expect(html_page.locator('#linksColumns input[value="核算状态"]')).to_be_disabled()
    html_page.locator('#linksColumns input[value="刷单金额_分"]').uncheck()
    expect(grid.locator('.tabulator-col[tabulator-field="刷单金额_分"]')).to_be_hidden()
    html_page.get_by_role("button", name="重置筛选").click()
    expect(html_page.locator("#linkCount")).to_have_text("匹配 3 / 3 个链接")
    grid.locator('.tabulator-col[tabulator-field="销售额_分"]').click()
    expect(grid.locator(".tabulator-row").first).to_contain_text("P2")
    html_page.locator('#links [data-preset="overview"]').click()
    expect(grid.locator(".tabulator-row").first).to_contain_text("P2")
    grid.get_by_role("button", name="详情").first.click()
    expect(html_page.get_by_role("dialog")).to_be_visible()
    expect(html_page.locator("#detailFields")).to_contain_text("¥-3.00")
    expect(html_page.locator("#detailFields")).to_contain_text("<img src=x")
    assert html_page.locator("img").count() == 0
    assert html_page.evaluate("document.body.dataset.pwned") is None
    assert html_page.locator('#detailFields a').get_attribute("href").startswith(
        "https://item.taobao.com/"
    )
    html_page.keyboard.press("Escape")
    expect(html_page.get_by_role("dialog")).to_be_hidden()


def test_empty_states_and_provisional(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(report(tmp_path, empty=True, status=RunStatus.PROVISIONAL).as_uri())
    expect(html_page.get_by_role("note")).to_contain_text("不得作为最终利润")
    expect(html_page.locator("#keyMetrics")).to_contain_text("已核算部分经营贡献利润")
    for view, text in (("daily", "本期暂无每日数据"), ("products", "本期暂无产品数据"),
                       ("links", "没有匹配的链接")):
        open_view(html_page, view)
        expect(html_page.locator(f"#{view}Grid")).to_contain_text(text)
    expect(html_page.locator("#linkCount")).to_have_text("匹配 0 / 0 个链接")
    open_view(html_page, "daily")
    for group in ("sales", "profit", "promotion", "orders"):
        html_page.locator(f'[data-daily-chart="{group}"]').click()
        expect(html_page.locator("#dailyChart")).to_be_hidden()
        expect(html_page.locator("#dailyChartEmpty")).to_be_visible()


@pytest.mark.parametrize("values", [[100], [0], [100, None, -200, None, 0]])
def test_echarts_daily_points_missing_values_and_keyboard(
    tmp_path: Path, html_page: Page, values: list[int | None]
) -> None:
    daily = [{"日期": f"2026-08-{i + 1:02}", "销售额_分": value}
             for i, value in enumerate(values)]
    html_page.goto(report(tmp_path, daily=daily).as_uri())
    open_view(html_page, "daily")
    expect(html_page.locator("#dailyChart svg")).to_be_visible()
    series = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#dailyChart')).getOption().series[0]"
    )
    assert series["data"] == [v / 100 if v is not None else None for v in values]
    assert series["connectNulls"] is False
    assert series["showSymbol"] is True
    html_page.locator("#dailyChart").focus()
    html_page.keyboard.press("Home")
    expect(html_page.locator("#dailyChartReadout")).to_contain_text("2026-08-01")
    expect(html_page.locator("#dailyChartReadout")).to_contain_text(
        "¥0.00" if values[0] == 0 else "¥1.00"
    )
    html_page.locator('[data-daily-chart="orders"]').click()
    axes = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#dailyChart')).getOption().yAxis"
    )
    assert len(axes) == 2


def test_waterfall_and_diagnostic_clicks(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(report(tmp_path).as_uri())
    expect(html_page.locator("#profitChart svg")).to_be_visible()
    expect(html_page.locator("#profitValues")).to_contain_text("¥46.70")
    html_page.evaluate("""echarts.getInstanceByDom(document.querySelector('#profitChart'))
        .dispatchAction({type: 'showTip', seriesIndex: 0, dataIndex: 2})""")
    expect(html_page.locator("#profitChart")).to_contain_text("占已核算净销售额 30.00%")
    open_view(html_page, "products")
    html_page.evaluate("""echarts.getInstanceByDom(document.querySelector('#productChart'))
        .trigger('click', {dataIndex: 0, seriesIndex: 0})""")
    expect(html_page.locator("#productCount")).to_have_text("匹配 1 / 3 个产品")
    open_view(html_page, "links")
    expect(html_page.locator("#linkRankNote")).to_contain_text("排除 1")
    html_page.evaluate("""echarts.getInstanceByDom(document.querySelector('#linkTopChart'))
        .trigger('click', {data: {value: 46.7, linkId: 'P1'}, seriesIndex: 0})""")
    expect(html_page.locator("#linkCount")).to_have_text("匹配 1 / 3 个链接")
    html_page.get_by_role("button", name="重置筛选").click()
    expect(html_page.locator("#linkCount")).to_have_text("匹配 3 / 3 个链接")


@pytest.mark.parametrize("metric,field,scale", [
    ("profit", "含推广经营贡献利润_分", 100), ("sales", "销售额_分", 100),
    ("spend", "推广花费_分", 100), ("spendShare", "推广费率", .01),
    ("refund", "订单批次成功退款_分", 100), ("refundRate", "退款率", .01),
])
def test_link_top_bottom_ranks_and_preserve_table_state(
    tmp_path: Path, html_page: Page, metric: str, field: str, scale: float,
) -> None:
    rows = [{"商品ID": f"P{i:02}", "商品标题": f"链接{i}", "核算状态": "已核算",
             field: i - 2, "销售额_分": i - 2, "含推广经营贡献利润_分": i - 2}
            for i in range(25)]
    rows.append({"商品ID": "missing", "核算状态": "已核算", field: None})
    html_page.goto(report(tmp_path, links=rows).as_uri())
    open_view(html_page, "links")
    html_page.locator('#links [data-preset="cost"]').click()
    html_page.get_by_label("商品搜索", exact=True).fill("P")
    html_page.get_by_label("链接排行指标").select_option(metric)
    for side, expected in (("Top", list(range(24, 14, -1))), ("Bottom", list(range(10)))):
        items = html_page.evaluate(
            f"echarts.getInstanceByDom(document.querySelector('#link{side}Chart'))"
            ".getOption().series[0].data"
        )
        assert [item["linkId"] for item in items] == [f"P{i:02}" for i in expected]
        assert [item["value"] for item in items] == pytest.approx(
            [(i - 2) / scale for i in expected]
        )
    expect(html_page.get_by_label("商品搜索", exact=True)).to_have_value("P")
    expect(html_page.locator('#links [data-preset="cost"]')
           ).to_have_attribute("aria-pressed", "true")
    if metric == "spendShare":
        expect(html_page.locator("#linkRankNote")).to_contain_text("已核算净销售额")
    html_page.get_by_role("button", name="重置筛选").click()
    expect(html_page.locator("#linkRankNote")).to_contain_text("排除 1")
    html_page.get_by_label("商品搜索", exact=True).fill("不存在")
    expect(html_page.locator("#linkTopChartEmpty")).to_be_visible()
    expect(html_page.locator("#linkBottomChartEmpty")).to_be_visible()


def test_missing_waterfall_does_not_invent_zero(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(report(tmp_path, summary={}).as_uri())
    expect(html_page.locator("#profitChartEmpty")).to_contain_text("数据不完整")
    expect(html_page.locator("#profitChart")).to_be_hidden()


def test_profit_formula_terms_operators_and_result(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(report(tmp_path, status=RunStatus.PROVISIONAL).as_uri())
    formula = html_page.locator("#profitFormula")
    expect(formula.locator(".value")).to_have_count(10)
    expect(formula.locator(".primary")).to_contain_text("已核算部分经营贡献利润")
    expect(formula.locator(".primary")).to_contain_text("¥46.70")
    assert formula.locator(".formula-operator").all_text_contents() == ["=", *["-"] * 8]
    assert formula.locator(".value > span").all_text_contents() == [
        "已核算部分经营贡献利润", "已核算销售额", "订单批次退款", "货品成本", "运费",
        "刷单成本", "平台扣点（估算）", "综合税赋（估算）", "关闭已发货损失", "推广花费",
    ]
    for width in (390, 768, 1440, 1920):
        html_page.set_viewport_size({"width": width, "height": 1000})
        assert formula.evaluate("node => node.scrollWidth <= node.clientWidth")
        assert formula.locator(".formula-unit").evaluate_all(
            """units => units.every(unit => {
                const op = unit.querySelector('.formula-operator');
                const card = unit.querySelector('.value');
                return !op || (Math.abs(op.getBoundingClientRect().top -
                    card.getBoundingClientRect().top) < 1);
            })"""
        )
    expect(html_page.locator("#summaryMetrics")).to_contain_text("退款与关闭")
    expect(html_page.locator("#summaryMetrics")).to_contain_text("推广归因")


def test_overview_bi_shares_and_signed_bars(tmp_path: Path, html_page: Page) -> None:
    rows = [{"产品名称": f"产品{i}", "销售额_分": (i + 1) * 100,
             "含推广经营贡献利润_分": (i + 1) * 10,
             "经营贡献利润率状态": "已核算"} for i in range(8)]
    rows += [{"产品名称": "亏损产品", "销售额_分": 0,
              "含推广经营贡献利润_分": -500, "经营贡献利润率状态": "已核算"},
             {"产品名称": "待核算产品", "销售额_分": None,
              "含推广经营贡献利润_分": 99999, "经营贡献利润率状态": "待核算"}]
    html_page.goto(report(tmp_path, products=rows).as_uri())
    for id_ in ("salesMixChart", "profitMixChart", "productProfitChart", "costChart"):
        expect(html_page.locator(f"#{id_} svg")).to_be_visible()
    for id_, total in (("salesMixChart", 36), ("profitMixChart", 3.6)):
        items = html_page.evaluate(
            f"echarts.getInstanceByDom(document.querySelector('#{id_}')).getOption().series[0].data"
        )
        assert len(items) == 7
        assert sum(item["value"] for item in items) == pytest.approx(total)
        assert items[-1]["name"] == "其余 2 个产品"
    expect(html_page.locator("#profitMixNote")).to_contain_text("正利润合计")
    expect(html_page.locator("#profitMixNote")).to_contain_text("排除 2")
    bars = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#productProfitChart'))"
        ".getOption().series[0].data"
    )
    assert bars[0]["value"] == -5
    assert 999.99 not in [bar["value"] for bar in bars]
    html_page.evaluate("""echarts.getInstanceByDom(document.querySelector('#profitMixChart'))
        .dispatchAction({type: 'showTip', seriesIndex: 0, dataIndex: 0})""")
    expect(html_page.locator("#profitMixChart")).to_contain_text("22.22%")


def test_overview_bi_empty_and_missing_costs(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(report(tmp_path, empty=True, summary={}).as_uri())
    for id_ in ("salesMixChart", "profitMixChart", "productProfitChart", "costChart"):
        expect(html_page.locator(f"#{id_}")).to_be_hidden()
        expect(html_page.locator(f"#{id_}Empty")).to_be_visible()
    html_page.goto(report(tmp_path, summary={"已核算运费_分": 100}).as_uri())
    expect(html_page.locator("#costNote")).to_contain_text("缺失 6")
    items = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#costChart')).getOption().series[0].data"
    )
    assert [item["value"] for item in items] == [1]
    html_page.goto(report(tmp_path, products=[{
        "产品名称": "零值产品", "销售额_分": 0, "含推广经营贡献利润_分": 0,
        "经营贡献利润率状态": "已核算",
    }], summary={"已核算运费_分": 0}).as_uri())
    for id_ in ("salesMixChart", "profitMixChart", "costChart"):
        expect(html_page.locator(f"#{id_}Empty")).to_be_visible()


def test_small_link_ranks_ties_and_exact_click(tmp_path: Path, html_page: Page) -> None:
    rows = [{"商品ID": id_, "商品标题": "同值链接", "核算状态": "已核算",
             "含推广经营贡献利润_分": 0} for id_ in ("P10", "P1")]
    rows.append({"商品ID": "pending", "核算状态": "成本或运费缺失",
                 "含推广经营贡献利润_分": 999999})
    html_page.goto(report(tmp_path, links=rows).as_uri())
    open_view(html_page, "links")
    expect(html_page.get_by_label("链接排行指标")).to_have_value("profit")
    for side in ("Top", "Bottom"):
        ids = html_page.evaluate(
            f"echarts.getInstanceByDom(document.querySelector('#link{side}Chart'))"
            ".getOption().series[0].data.map(d => d.linkId)"
        )
        assert ids == ["P1", "P10"]
    html_page.evaluate("""echarts.getInstanceByDom(document.querySelector('#linkBottomChart'))
        .trigger('click', {data: {linkId: 'P1'}, seriesIndex: 0})""")
    expect(html_page.locator("#linkCount")).to_have_text("匹配 1 / 3 个链接")


@pytest.mark.parametrize("sales,refund,cost,expected", [
    (10000, 2000, 3000, "占已核算净销售额 37.50%"),
    (10000, 10000, 3000, "占已核算净销售额 暂无比例"),
    (10000, 12000, 3000, "占已核算净销售额 -150.00%"),
    (None, 2000, 3000, "占已核算净销售额 暂无比例"),
    (10000, 2000, None, "占已核算净销售额 暂无比例"),
])
def test_overview_shares_explicit_bases_and_missing_values(
    tmp_path: Path, html_page: Page, sales: int | None, refund: int,
    cost: int | None, expected: str,
) -> None:
    summary = {
        "已付款销售额_分": 20000, "真实销售额_分": 16000,
        "刷单金额_分": 1000, "订单批次成功退款金额_分": 3000,
        "已核算销售额_分": sales, "已核算订单批次成功退款_分": refund,
        "已核算货品成本_分": cost, "经营贡献利润率": Decimal("0.1234"),
        "推广投产比": Decimal("2.5"),
    }
    html_page.goto(report(tmp_path, summary=summary).as_uri())
    sales_values = html_page.locator("#salesValues .value")
    expect(sales_values.filter(has=html_page.get_by_text("真实销售额", exact=True))
           ).to_contain_text("占已付款销售额 80.00%")
    expect(sales_values.filter(has=html_page.get_by_text("减：刷单金额", exact=True))
           ).to_contain_text("占已付款销售额 5.00%")
    profit_values = html_page.locator("#profitValues .value")
    expect(profit_values.filter(has=html_page.get_by_text("货品成本", exact=True))
           ).to_contain_text(expected)
    expect(profit_values.filter(has=html_page.get_by_text("订单批次退款", exact=True))
           ).to_contain_text("占已核算销售额 " + (
               "暂无比例" if sales is None else f"{refund / sales * 100:.2f}%"
           ))
    expect(profit_values.filter(has=html_page.get_by_text("含推广经营贡献利润", exact=True))
           ).to_contain_text("利润率 12.34%")
    expect(html_page.locator("#summaryMetrics")).to_contain_text("推广投产比 2.50x")


def test_product_presets_and_profit_rank_exclude_incomplete(
    tmp_path: Path, html_page: Page
) -> None:
    html_page.goto(report(tmp_path).as_uri())
    open_view(html_page, "products")
    html_page.get_by_label("产品搜索", exact=True).fill("产品一")
    html_page.locator('#products [data-preset="cost"]').click()
    expect(html_page.locator("#productCount")).to_have_text("匹配 1 / 3 个产品")
    expect(html_page.locator('#productsGrid .tabulator-col[tabulator-field="平台扣点_分"]')
           ).to_be_visible()
    html_page.locator('#products').get_by_label("排序指标").select_option("profit")
    categories = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#productChart')).getOption().yAxis[0].data"
    )
    assert "待核算产品" not in categories
    assert set(categories) == {"产品一", "产品二"}


def test_product_metrics_columns_and_filtered_insights(tmp_path: Path, html_page: Page) -> None:
    rows = [
        {"产品名称": "产品一", "商品链接数": 2, "销售额_分": 20000, "真实销售额_分": 17000,
         "订单批次成功退款_分": 3000, "推广花费_分": 1000, "推广归因成交金额_分": 2500,
         "推广投产比": 2.5, "含推广经营贡献利润_分": 4000,
         "经营贡献利润率状态": "已核算"},
        {"产品名称": "产品二", "销售额_分": 10000, "订单批次成功退款_分": None,
         "推广花费_分": 500, "推广归因成交金额_分": None, "经营贡献利润率状态": "待核算"},
        {"产品名称": "产品三", "经营贡献利润率状态": "净销售额非正"},
    ]
    html_page.goto(report(tmp_path, products=rows).as_uri())
    open_view(html_page, "products")
    for field in ("商品链接数", "真实销售额_分", "订单批次成功退款_分", "推广投产比"):
        expect(html_page.locator(f'#productsGrid .tabulator-col[tabulator-field="{field}"]')
               ).to_be_visible()
    for chart in ("productSalesChart", "productPromotionChart", "productShareChart"):
        expect(html_page.locator(f"#{chart} svg")).to_be_visible()
    series = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#productSalesChart')).getOption().series"
    )
    assert series[0]["data"] == [200, 100]
    assert series[1]["data"] == [30, None]
    shares = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#productShareChart'))"
        ".getOption().series[0].data"
    )
    assert {item["name"]: item["value"] for item in shares} == {"产品一": 40}
    expect(html_page.locator("#productShareNote")).to_contain_text("排除 2")
    html_page.get_by_label("产品搜索", exact=True).fill("产品二")
    expect(html_page.locator("#productInsightNote")).to_contain_text("当前筛选 1 个产品")
    categories = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#productPromotionChart'))"
        ".getOption().yAxis[0].data"
    )
    assert categories == ["产品二"]
    html_page.get_by_role("button", name="重置产品筛选").click()
    expect(html_page.locator("#productInsightNote")).to_contain_text("当前筛选 3 个产品")
    html_page.get_by_label("产品搜索", exact=True).fill("不存在")
    for chart in ("productSalesChart", "productPromotionChart", "productShareChart"):
        expect(html_page.locator(f"#{chart}Empty")).to_be_visible()


def test_product_share_is_profit_amount_not_product_count(tmp_path: Path, html_page: Page) -> None:
    rows = [{"产品名称": name, "含推广经营贡献利润_分": amount,
             "经营贡献利润率状态": status} for name, amount, status in (
        ("产品甲", 3000, "已核算"), ("产品乙", 1000, "已核算"),
        ("亏损产品", -1000, "已核算"), ("待核算产品", 5000, "待核算"),
    )]
    html_page.goto(report(tmp_path, products=rows).as_uri())
    open_view(html_page, "products")
    expect(html_page.locator("#productShareChart svg")).to_be_visible()
    html_page.evaluate("""echarts.getInstanceByDom(document.querySelector('#productShareChart'))
        .dispatchAction({type: 'showTip', seriesIndex: 0, dataIndex: 0})""")
    expect(html_page.locator("#productShareChart")).to_contain_text("75.00%")
    expect(html_page.locator("#productShareNote")).to_contain_text("¥40.00")
    expect(html_page.locator("#productShareNote")).to_contain_text("排除 2")


def test_product_rank_mirrors_absolute_profit_and_keeps_true_sign(
    tmp_path: Path, html_page: Page
) -> None:
    rows = [{"产品名称": name, "销售额_分": sales, "含推广经营贡献利润_分": profit,
             "经营贡献利润率状态": status} for name, sales, profit, status in (
        ("盈利产品", 10000, 2000, "已核算"), ("亏损产品", 9000, -1000, "已核算"),
        ("待核算产品", 8000, 5000, "待核算"), ("零利润产品", 7000, 0, "已核算"),
    )]
    html_page.goto(report(tmp_path, products=rows).as_uri())
    open_view(html_page, "products")
    expect(html_page.locator("#productChart svg")).to_be_visible()
    option = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#productChart')).getOption()"
    )
    assert len(option["series"]) == 2
    assert option["xAxis"][0]["inverse"] is True
    assert option["xAxis"][0]["min"] == 0
    assert option["xAxis"][1]["min"] == 0
    assert option["yAxis"][0]["position"] == "left"
    origins = html_page.evaluate("""() => {
        const chart = echarts.getInstanceByDom(document.querySelector('#productChart'));
        return [chart.convertToPixel({xAxisIndex: 0}, 0),
                chart.convertToPixel({xAxisIndex: 1}, 0)];
    }""")
    assert origins[0] == pytest.approx(origins[1], abs=1)
    assert [item["value"] for item in option["series"][0]["data"]] == [20, 10, None, 0]
    assert [item["value"] for item in option["series"][1]["data"]] == [100, 90, 80, 70]
    assert option["series"][0]["data"][1]["itemStyle"]["color"] == "#b42318"
    html_page.evaluate("""echarts.getInstanceByDom(document.querySelector('#productChart'))
        .dispatchAction({type: 'showTip', seriesIndex: 0, dataIndex: 1})""")
    expect(html_page.locator("#productChart")).to_contain_text("¥-10.00")
    html_page.get_by_label("排序指标").select_option("profit")
    categories = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#productChart')).getOption().yAxis[0].data"
    )
    assert categories == ["盈利产品", "零利润产品", "亏损产品"]
    html_page.evaluate("""echarts.getInstanceByDom(document.querySelector('#productChart'))
        .trigger('click', {seriesIndex: 1, dataIndex: 2})""")
    expect(html_page.locator("#productCount")).to_have_text("匹配 1 / 4 个产品")


@pytest.mark.parametrize("profit", [4670, 0, -5330])
def test_waterfall_preserves_positive_zero_and_negative_profit(
    tmp_path: Path, html_page: Page, profit: int
) -> None:
    summary = {
        "已核算销售额_分": 10000, "已核算订单批次成功退款_分": 0,
        "已核算货品成本_分": 3000, "已核算运费_分": 500,
        "已核算刷单成本_分": 1000, "已核算平台扣点_分": 600,
        "已核算综合税赋_分": 230, "关闭已发货损失_分": 0,
        "推广花费_分": 4670 - profit, "含推广经营贡献利润_分": profit,
    }
    html_page.goto(report(tmp_path, summary=summary).as_uri())
    expect(html_page.locator("#profitChart svg")).to_be_visible()
    expect(html_page.locator("#profitValues")).to_contain_text(
        "¥" + f"{profit / 100:,.2f}"
    )
    segments = html_page.evaluate(
        "echarts.getInstanceByDom(document.querySelector('#profitChart')).getOption().series[0].data"
    )
    assert segments[-1][2] == profit / 100
    assert segments[-2][2] == profit / 100
    assert segments[0][2] == 100


def test_packagers_include_report_resources() -> None:
    root = Path(__file__).resolve().parents[1]
    for filename in ("build-windows.ps1", "build-cli-skill.ps1", "build-macos-x86_64.sh"):
        script = (root / "scripts" / filename).read_text(encoding="utf-8")
        assert ('"--collect-data", "order_profit"' in script or
                '--collect-data order_profit' in script)


def test_light_theme_responsive_and_default_columns_fit(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(report(tmp_path).as_uri())
    light = html_page.evaluate("getComputedStyle(document.body).backgroundColor")
    html_page.emulate_media(color_scheme="dark", reduced_motion="reduce")
    assert html_page.evaluate("getComputedStyle(document.body).backgroundColor") == light
    for width in (390, 768, 1280, 1440, 1920, 2560, 1440):
        html_page.set_viewport_size({"width": width, "height": 1000})
        for view in ("overview", "daily", "products", "links"):
            open_view(html_page, view)
            html_page.wait_for_function("document.documentElement.scrollWidth <= innerWidth")
            if width >= 1440 and view in ("products", "links"):
                holder = html_page.locator(f"#{view}Grid .tabulator-tableholder")
                expect(holder).to_be_visible()
                html_page.wait_for_function(
                    """selector => {
                        const n = document.querySelector(selector);
                        return n.scrollWidth <= n.clientWidth + 1;
                    }""", arg=f"#{view}Grid .tabulator-tableholder"
                )
