"""Self-contained, read-only ECharts / Tabulator operating report."""

from __future__ import annotations

import html
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any

import pandas as pd

from order_profit import __version__
from order_profit.config import RunConfig


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        try:
            converted = float(value)
        except (OverflowError, ValueError):
            return None
        return converted if math.isfinite(converted) else None
    if isinstance(value, (str, list, dict)):
        return value
    if pd.isna(value):
        return None
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(key): _json_value(value) for key, value in row.items()}
            for row in frame.to_dict("records")]


def _json_for_script(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _asset(name: str) -> str:
    return files("order_profit").joinpath("web", name).read_text(encoding="utf-8")


def _inline_script(script: str) -> str:
    return re.sub(r"</script", r"<\\/script", script, flags=re.IGNORECASE)


def _grid_toolbar(view: str) -> str:
    return f"""<div class="grid-toolbar" aria-label="明细显示设置">
      <div class="presets" role="group" aria-label="列视图">
        <button data-preset="overview" aria-pressed="true" class="active">经营概览</button>
        <button data-preset="cost" aria-pressed="false">成本明细</button>
        <button data-preset="all" aria-pressed="false">完整明细</button>
      </div>
      <details class="column-picker"><summary>显示列</summary>
        <div id="{view}Columns" class="column-options"></div></details>
      <span class="hint">点击行或“详情”核对全部字段</span>
    </div>"""


def write_html(result: Any, config: RunConfig, path: Path) -> None:
    analysis = result.analysis
    status = result.reconciliation.status.value
    payload = {"summary": {key: _json_value(value) for key, value in analysis.summary.items()},
               "daily": _records(analysis.daily), "products": _records(analysis.products),
               "links": _records(analysis.links), "sku": _records(analysis.sku),
               "provisional": status == "PROVISIONAL"}
    notice = (
        '<div class="notice" role="note">成本或运费尚未补齐，利润仅反映已核算部分，'
        '不得作为最终利润。请补齐待补清单后重新生成报告。</div>'
        if status == "PROVISIONAL" else ""
    )
    status_label = "待补成本 / 运费" if status == "PROVISIONAL" else "核算完整"
    licenses = "\n\n".join(_asset("vendor/" + name) for name in (
        "echarts-LICENSE.txt", "echarts-NOTICE.txt", "tabulator-LICENSE.txt"
    ))
    vendor_script = "\n".join(_asset("vendor/" + name) for name in (
        "echarts.min.js", "tabulator.min.js"
    ))
    nav = "\n".join(
        f'<button data-view="{view}" aria-controls="{view}" '
        f'aria-pressed="{str(index == 0).lower()}" '
        f'class="{"active" if index == 0 else ""}">{label}</button>'
        for index, (view, label) in enumerate((
            ("overview", "经营总览"), ("daily", "每日经营"),
            ("products", "产品分析"), ("links", "链接分析")
        ))
    )
    filters = "".join(
        f'<label>{label}<select id="{key}"><option value="">{all_label}</option>'
        + "".join(f'<option>{html.escape(option)}</option>' for option in options)
        + '</select></label>'
        for key, label, all_label, options in (
            ("productFilter", "产品", "全部产品", []),
            ("sabc", "SABC等级", "全部 SABC", []),
            ("profit", "盈亏状态", "全部盈亏", ["盈利", "亏损", "持平", "待核算"]),
            ("coverage", "数据覆盖", "全部覆盖", ["订单+推广", "仅订单", "仅推广"]),
            ("accounting", "核算状态", "全部核算状态", ["已核算", "成本或运费缺失"]),
        )
    )
    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>店铺经营复盘</title>
<style>{_asset('vendor/tabulator.min.css')}</style><style>{_asset('report.css')}</style>
</head><body>
<header><div><h1>店铺经营复盘</h1>
<p>{config.start_date.isoformat()} 至 {config.end_date.isoformat()}</p></div>
<div class="meta"><b class="status {status.lower()}">{html.escape(status)} · {status_label}</b>
<p>{html.escape(config.platform.value)}　平台费 {config.platform_fee_rate:.2%}
　税赋 {config.tax_rate:.2%}</p></div></header>
<nav aria-label="报告视图">{nav}</nav>
<main>{notice}<div id="reportError" class="notice" role="alert" hidden></div>
<section id="overview" class="view">
<div id="keyMetrics" class="key-metrics" aria-label="核心经营指标"></div>
<section aria-labelledby="insightsTitle"><div class="insights-heading">
<h2 id="insightsTitle">经营结构与贡献</h2>
<p class="hint">从产品结构、盈利来源和费用构成定位经营重点。</p></div>
<div class="insights-grid">
<section class="panel"><h3>产品销售占比</h3><p id="salesMixNote" class="hint"></p>
<div id="salesMixChart" class="chart" role="img" aria-label="产品销售占比环形图"></div>
<p id="salesMixChartEmpty" class="empty" hidden>暂无销售额为正的产品</p></section>
<section class="panel"><h3>产品盈利贡献占比</h3><p id="profitMixNote" class="hint"></p>
<div id="profitMixChart" class="chart" role="img" aria-label="产品盈利贡献占比环形图"></div>
<p id="profitMixChartEmpty" class="empty" hidden>暂无核算完整且盈利的产品</p></section>
<section class="panel"><h3>产品盈亏对比</h3><p id="productProfitNote" class="hint"></p>
<div id="productProfitChart" class="chart" role="img" aria-label="产品盈亏柱图"></div>
<p id="productProfitChartEmpty" class="empty" hidden>暂无核算完整的产品利润数据</p></section>
<section class="panel"><h3>成本费用构成</h3><p id="costNote" class="hint"></p>
<div id="costChart" class="chart" role="img" aria-label="成本费用柱图"></div>
<p id="costChartEmpty" class="empty" hidden>暂无有效的非零成本费用数据</p></section>
</div></section>
<section class="panel"><h2>全部订单销售链</h2><p class="hint">按订单付款日期归属</p>
<div id="salesValues" class="value-grid"></div></section>
<section class="panel"><h2>已核算利润瀑布</h2>
<p class="hint">已核算销售额扣除退款、货品及各项费用；不包含未核算部分。</p>
<div id="profitChart" class="chart" role="img" aria-label="已核算利润瀑布图"></div>
<p id="profitChartEmpty" class="empty" hidden></p><div id="profitValues" class="profit-breakdown">
<h3>利润计算公式</h3><p class="hint">按已核算部分逐项扣减，金额单位：元。</p>
<div id="profitFormula" class="formula-chain" aria-label="已核算利润计算公式"></div>
<div id="profitNet" class="formula-base"></div></div>
</section><section class="panel"><h2>经营补充指标</h2>
<div id="summaryMetrics" class="supplement-groups"></div></section>
<section class="panel"><h2>链接覆盖与风险</h2><div id="coverageValues" class="value-grid"></div>
<p class="hint">在链接分析中按核算、盈亏与覆盖状态定位问题，并核对运营动作。</p></section>
</section>
<section id="daily" class="view" hidden><section class="panel">
<h2 id="dailyChartTitle">销售表现</h2><p id="dailyChartPeriod" class="hint"></p>
<div class="presets" role="group" aria-label="每日趋势指标">
<button data-daily-chart="sales" aria-pressed="true" class="active">销售</button>
<button data-daily-chart="profit" aria-pressed="false">利润</button>
<button data-daily-chart="promotion" aria-pressed="false">推广</button>
<button data-daily-chart="orders" aria-pressed="false">订单与退款</button></div>
<div id="dailyChart" class="chart" tabindex="0" role="img"
 aria-label="每日趋势图，使用左右方向键、Home、End 查看每日数据"></div>
<p id="dailyChartEmpty" class="empty" hidden>本期暂无每日数据</p>
<p id="dailyChartReadout" role="status" aria-live="polite"></p></section>
{_grid_toolbar('daily')}<div id="dailyGrid" class="data-grid" aria-label="每日明细"></div></section>
<section id="products" class="view" hidden><h2>产品分析</h2>
<div class="filter-summary"><label>产品搜索<input id="productSearch" type="search"
 placeholder="产品名称"></label><span id="productCount" role="status"></span>
<button id="resetProducts">重置产品筛选</button></div>
<p id="productInsightNote" class="hint"></p><div class="insights-grid product-insights">
<section class="panel"><div class="chart-heading"><h3>产品排行</h3>
<label>排序指标<select id="productRank"><option value="sales">销售额</option>
<option value="profit">经营贡献利润（核算完整）</option></select></label></div>
<p id="productRankNote" class="hint">左侧利润（绿色盈利、红色亏损），右侧销售额。
柱长按绝对值展示，左右独立刻度；点击条形筛选明细。</p>
<div id="productChart" class="chart" role="img" aria-label="产品排行"></div>
<p id="productChartEmpty" class="empty" hidden>本期暂无符合排行口径的产品</p></section>
<section class="panel"><h3>销售与退款对比</h3>
<p class="hint">当前筛选按销售额展示前 10，退款为订单批次成功退款；缺失值不画成零。</p>
<div id="productSalesChart" class="chart" role="img" aria-label="产品销售退款柱图"></div>
<p id="productSalesChartEmpty" class="empty" hidden>暂无有效的销售或退款数据</p></section>
<section class="panel"><h3>推广投入与归因成交</h3>
<p class="hint">当前筛选按推广花费展示前 10，归因成交不计入订单销售额。产品推广为分摊估算。</p>
<div id="productPromotionChart" class="chart" role="img" aria-label="产品推广投入归因柱图"></div>
<p id="productPromotionChartEmpty" class="empty" hidden>暂无有效的推广金额数据</p></section>
<section class="panel"><h3>各产品盈利贡献占比</h3>
<p id="productShareNote" class="hint"></p>
<div id="productShareChart" class="chart" role="img" aria-label="各产品盈利贡献占比环形图"></div>
<p id="productShareChartEmpty" class="empty" hidden>当前筛选下暂无核算完整且盈利的产品</p>
</section></div>
{_grid_toolbar('products')}<div id="productsGrid" class="data-grid" aria-label="产品明细"></div>
</section>
<section id="links" class="view" hidden><h2>链接分析</h2>
<div class="controls"><label>商品搜索<input id="search" type="search"
 placeholder="商品ID或标题"></label>{filters}<label>排序方式<select id="sort">
<option value="含推广经营贡献利润_分">经营贡献利润：高到低</option>
<option value="销售额_分">销售额：高到低</option>
<option value="经营贡献利润率">经营贡献利润率：高到低</option>
<option value="推广花费_分">推广花费：高到低</option>
<option value="推广投产比">推广投产比：高到低</option>
<option value="退款率">退款率：高到低</option></select></label></div>
<section class="panel"><div class="chart-heading"><h3>链接指标排行</h3>
<label>链接排行指标<select id="linkRank"><option value="profit">利润</option>
<option value="sales">销售额</option><option value="spend">推广花费</option>
<option value="spendShare">推广占比</option><option value="refund">退款金额</option>
<option value="refundRate">退款率</option></select></label></div>
<p id="linkRankNote" class="hint"></p><div class="link-rank-grid">
<section><h4>前 10（高到低）</h4>
<div id="linkTopChart" class="chart" role="img" aria-label="链接指标前10排行"></div>
<p id="linkTopChartEmpty" class="empty" hidden>当前筛选下暂无有效指标数据</p></section>
<section><h4>后 10（低到高）</h4>
<div id="linkBottomChart" class="chart" role="img" aria-label="链接指标后10排行"></div>
<p id="linkBottomChartEmpty" class="empty" hidden>当前筛选下暂无有效指标数据</p>
</section></div></section>
<div class="filter-summary"><span id="linkCount" role="status" aria-live="polite"></span>
<button id="resetFilters">重置筛选</button></div>
{_grid_toolbar('links')}<div id="linksGrid" class="data-grid" aria-label="链接明细"></div>
</section></main>
<dialog id="rowDetail" aria-labelledby="detailTitle"><div class="detail-heading">
<h2 id="detailTitle">完整明细</h2><button id="closeDetail">关闭详情</button></div>
<dl id="detailFields"></dl></dialog>
<footer>推广归因成交金额不计入订单销售额。平台扣点与综合税赋为管理估算值。
SABC 阈值 {config.s_profit_share:.0%}/{config.a_profit_share:.0%}。
程序版本 {html.escape(__version__)}。输入订单 {html.escape(config.orders.name)}。
<details><summary>组件版本与许可证</summary>
<p>ECharts 6.0.0 / Tabulator 6.3.1</p><pre id="libraryLicenses">{html.escape(licenses)}</pre>
</details></footer><noscript>请启用 JavaScript 查看图表和明细。
核算底稿请查看同目录 Excel。</noscript>
<script>{_inline_script(vendor_script)}</script>
<script id="reportData" type="application/json">{_json_for_script(payload)}</script>
<script>{_inline_script(_asset('report.js'))}</script>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8", newline="\n")
