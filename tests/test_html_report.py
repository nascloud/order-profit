from __future__ import annotations

import math
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
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def html_page(html_browser: Browser) -> Iterator[Page]:
    page = html_browser.new_page()
    try:
        yield page
    finally:
        page.close()


def _daily_report(
    tmp_path: Path, daily: list[dict[str, object]], status: RunStatus = RunStatus.FINAL
) -> Path:
    config = RunConfig(
        orders=tmp_path / "orders.xlsx",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        platform=Platform.TMALL,
        output_dir=tmp_path / "output",
    )
    result = SimpleNamespace(
        analysis=SimpleNamespace(
            summary={},
            links=pd.DataFrame(),
            daily=pd.DataFrame(daily),
            products=pd.DataFrame(),
            sku=pd.DataFrame(),
        ),
        reconciliation=SimpleNamespace(status=status),
    )
    path = tmp_path / "daily-report.html"
    write_html(result, config, path)
    return path

def test_html_escapes_business_text_and_embeds_safe_json(
    tmp_path: Path, html_page: Page
) -> None:
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
            sku=pd.DataFrame(
                [{"商家编码": "SKU-1", "产品名称": "产品一", "购买数量": 1, "销售额_分": 10000}]
            ),
        ),
        reconciliation=SimpleNamespace(status=RunStatus.FINAL),
    )
    path = tmp_path / "report.html"

    write_html(result, config, path)
    html_page.goto(path.as_uri())
    expect(html_page.locator("#keyMetrics .primary")).to_contain_text("¥46.70")
    expect(html_page.locator("#keyMetrics")).to_contain_text("46.70%")
    html_page.locator('nav [data-view="links"]').click()
    expect(html_page.locator("#rows")).to_contain_text(links.iloc[0]["商品标题"])
    assert html_page.locator("img").count() == 0
    assert html_page.evaluate("document.body.dataset.pwned") is None
    expect(html_page.locator("#linkCount")).to_have_text("匹配 1 / 1 个链接")
    html_page.get_by_label("商品搜索", exact=True).fill("不存在的商品")
    expect(html_page.locator("#linkCount")).to_have_text("匹配 0 / 1 个链接")
    html_page.get_by_role("button", name="重置筛选").click()
    expect(html_page.locator("#linkCount")).to_have_text("匹配 1 / 1 个链接")
    for width in (1280, 1440, 1920, 2560):
        html_page.set_viewport_size({"width": width, "height": 1000})
        for view in ("products", "links"):
            html_page.locator(f'nav [data-view="{view}"]').click()
            assert html_page.locator(f'#{view} .table-wrap').evaluate(
                "node => node.scrollWidth <= node.clientWidth + 1"
            )
    assert html_page.locator("main").bounding_box()["width"] > 2400


def test_report_provisional_warning(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(_daily_report(tmp_path, [], RunStatus.PROVISIONAL).as_uri())
    expect(html_page.get_by_role("note")).to_contain_text("不得作为最终利润")
    expect(html_page.locator("#keyMetrics .primary")).to_contain_text("已核算部分经营贡献利润")
    expect(html_page.locator(".status")).to_contain_text("PROVISIONAL")


def test_html_daily_chart_groups_accessibility_and_empty_state(
    tmp_path: Path, html_page: Page
) -> None:
    html_page.goto(_daily_report(tmp_path, []).as_uri())
    html_page.locator('nav [data-view="daily"]').click()
    for chart in ("sales", "profit", "promotion", "orders"):
        button = html_page.locator(f'[data-daily-chart="{chart}"]')
        button.click()
        expect(button).to_have_attribute("aria-pressed", "true")
        expect(html_page.locator("#dailyChart")).to_be_hidden()
        expect(html_page.locator("#dailyChartEmpty")).to_be_visible()


def test_report_visual_hierarchy_and_filter_empty_state(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(_daily_report(tmp_path, []).as_uri())
    expect(html_page.locator("#keyMetrics")).to_be_visible()
    expect(html_page.locator("#keyMetrics")).to_contain_text("销售额核算覆盖率")
    assert html_page.locator("#profitEquation").evaluate(
        "node => node.scrollWidth <= node.parentElement.clientWidth"
    )
    expect(html_page.locator('nav [data-view="overview"]')).to_have_attribute(
        "aria-pressed", "true"
    )
    html_page.get_by_role("button", name="链接分析", exact=True).click()
    expect(html_page.locator('nav [data-view="overview"]')).to_have_attribute(
        "aria-pressed", "false"
    )
    html_page.get_by_label("商品搜索", exact=True).fill("不存在的商品")
    expect(html_page.locator("#linkCount")).to_have_text("匹配 0 / 0 个链接")
    expect(html_page.locator("#rows")).to_contain_text("没有匹配的链接")
    html_page.get_by_role("button", name="重置筛选").click()
    expect(html_page.get_by_label("商品搜索", exact=True)).to_have_value("")
    html_page.get_by_role("button", name="产品分析", exact=True).click()
    expect(html_page.locator("#productTable")).to_contain_text("本期暂无产品数据")


def test_report_stays_light_and_fits_mobile(tmp_path: Path, html_page: Page) -> None:
    html_page.goto(_daily_report(tmp_path, []).as_uri())
    light = html_page.evaluate("getComputedStyle(document.body).backgroundColor")
    html_page.emulate_media(color_scheme="dark")
    dark = html_page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert light == dark
    for width in (390, 768, 1024):
        html_page.set_viewport_size({"width": width, "height": 844})
        for view in ("overview", "daily", "products", "links"):
            html_page.locator(f'nav [data-view="{view}"]').click()
            assert html_page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
    assert "@media print" not in html_page.locator("style").inner_text()


@pytest.mark.parametrize(
    ("values", "chart", "key", "isolated_indices", "line_indices"),
    [
        pytest.param([100], "sales", "销售额_分", [0], [], id="single-day"),
        pytest.param([0], "sales", "销售额_分", [0], [], id="zero-is-valid"),
        pytest.param(
            [100, None, -200, None, 0], "sales", "销售额_分", [0, 2, 4], [],
            id="isolated-values-with-gaps",
        ),
        pytest.param(
            [100, 200, None, 300], "sales", "销售额_分", [3], [(0, 1)],
            id="line-then-isolated-value",
        ),
        pytest.param(
            [100, 200, None, 300, 400], "sales", "销售额_分", [], [(0, 1), (3, 4)],
            id="separate-lines-across-gap",
        ),
        pytest.param([100], "orders", "订单批次成功退款_分", [0], [], id="right-axis-single-day"),
    ],
)
def test_html_daily_chart_renders_points_and_breaks_at_missing_values(
    tmp_path: Path,
    html_page: Page,
    values: list[int | None],
    chart: str,
    key: str,
    isolated_indices: list[int],
    line_indices: list[tuple[int, int]],
) -> None:
    daily = [
        {"日期": f"2026-08-{index + 1:02}", key: value}
        for index, value in enumerate(values)
    ]
    html_page.goto(_daily_report(tmp_path, daily).as_uri())
    html_page.locator('nav [data-view="daily"]').click()
    html_page.locator(f'[data-daily-chart="{chart}"]').click()
    expect(html_page.locator("#dailyChart")).to_be_visible()
    rendered = html_page.locator("#dailyChart").evaluate(
        """svg => ({
            width: svg.viewBox.baseVal.width,
            height: svg.viewBox.baseVal.height,
            dates: [...svg.querySelectorAll('.chart-date-label')].map(label =>
                Number(label.getAttribute('x'))),
            points: [...svg.querySelectorAll('.chart-point')].map(point => ({
                x: Number(point.getAttribute('cx')),
                y: Number(point.getAttribute('cy')),
                width: point.getBBox().width,
                height: point.getBBox().height
            })),
            lines: [...svg.querySelectorAll('.chart-line')].map(line => {
                const start = line.getPointAtLength(0);
                const end = line.getPointAtLength(line.getTotalLength());
                return {startX: start.x, endX: end.x};
            })
        })"""
    )
    assert len(rendered["points"]) == len(isolated_indices)
    for point, index in zip(rendered["points"], isolated_indices, strict=True):
        assert math.isfinite(point["x"]) and math.isfinite(point["y"])
        assert 0 < point["x"] < rendered["width"]
        assert 0 < point["y"] < rendered["height"]
        assert point["width"] > 0 and point["height"] > 0
        assert point["x"] == pytest.approx(rendered["dates"][index], abs=0.01)
    assert len(rendered["lines"]) == len(line_indices)
    for line, (start, end) in zip(rendered["lines"], line_indices, strict=True):
        assert line["startX"] == pytest.approx(rendered["dates"][start], abs=0.01)
        assert line["endX"] == pytest.approx(rendered["dates"][end], abs=0.01)
