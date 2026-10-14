from __future__ import annotations

import html
import json
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from order_profit.config import RunConfig

REPORT_CSS = r"""
:root {
  color-scheme: light;
  --ink: #17202a;
  --muted: #55656f;
  --line: #d9e0e5;
  --paper: #f5f7f8;
  --panel: #fdfefe;
  --tint: #eaf4ef;
  --brand: #176b54;
  --warn: #a65d00;
  --bad: #b42318;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  letter-spacing: 0;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 16px;
  padding: 26px max(28px, calc((100vw - 1400px) / 2 + 28px));
  background: #fff;
  border-bottom: 1px solid var(--line);
}
h1 { margin: 0 0 4px; font-size: 26px; letter-spacing: -.04em; }
.period { color: var(--muted); }
.status { display: inline-block; color: var(--brand); font-size: 13px; }
.status.provisional { color: #925000; }
.notice { margin: 0 0 20px; padding: 12px 16px; background: #fff3df;
  color: #764000; border-left: 3px solid var(--warn); border-radius: 8px; }
.meta { color: var(--muted); text-align: right; }
nav {
  position: sticky;
  top: 0;
  z-index: 3; /* Layers: table headers 1, sticky navigation 3. */
  display: flex;
  gap: 4px;
  padding: 6px max(28px, calc((100vw - 1400px) / 2 + 28px));
  background: #fff;
  border-bottom: 1px solid var(--line);
}
button, select, input { font: inherit; }
button { color: var(--ink); white-space: nowrap; }
button:active { transform: scale(.98); }
button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible {
  outline: 2px solid var(--brand); outline-offset: 3px;
}
a { color: var(--brand); }
nav button {
  padding: 12px 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  cursor: pointer;
}
nav button.active {
  color: var(--brand);
  border-bottom: 2px solid var(--brand);
  font-weight: 700;
}
main { max-width: 1400px; margin: auto; padding: 28px 28px 48px; }
.view[hidden] { display: none; }
.view-heading { margin-bottom: 18px; }
.view-heading h2 { margin: 0; font-size: 21px; }
.view-heading p { margin: 4px 0 0; color: var(--muted); }
.key-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 28px; background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; overflow: hidden; }
.key-metrics .metric { padding: 22px; border: 0; border-right: 1px solid var(--line); }
.key-metrics .metric:last-child { border-right: 0; }
.key-metrics .primary { background: var(--tint); }
.key-metrics .primary b { color: var(--brand); }
.key-metrics .metric b { font-size: clamp(22px, 2.2vw, 32px); }
.metric b, .term b, .rank-value, td { font-variant-numeric: tabular-nums; }
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  margin-top: 22px;
}
.metric {
  min-width: 0;
  padding: 16px 18px;
  border-bottom: 1px solid var(--line);
}
.metric span, .term span { color: var(--muted); }
.metric b { display: block; margin: 8px 0 4px; font-size: 24px; overflow-wrap: anywhere; }
.metric small, .term small { color: var(--muted); }
.negative { color: var(--bad) !important; }
.rankings { margin-top: 36px; }
.rankings-head, .calc-head {
  display: flex;
  justify-content: space-between;
  align-items: start;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 18px;
}
.rankings-head h2, .calc-head h2 { margin: 0; font-size: 18px; }
.rankings-head span, .calc-head span { color: var(--muted); font-size: 12px; }
.ranking-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.ranking {
  min-width: 0;
  padding: 18px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.ranking.risk h3 { color: var(--bad); }
.ranking h3 { margin: 0 0 12px; font-size: 15px; }
.ranking ol { margin: 0; padding: 0; list-style: none; counter-reset: rank; }
.ranking li {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  padding: 10px 0;
  border-top: 1px solid #edf0f2;
  counter-increment: rank;
}
.ranking li::before {
  display: grid;
  width: 18px;
  height: 18px;
  place-items: center;
  content: counter(rank);
  color: var(--muted);
  background: #eef3f1;
  border-radius: 50%;
  font-size: 10px;
  font-weight: 700;
}
.ranking li:first-child::before { color: #fff; background: var(--brand); }
.ranking.risk li:first-child::before { background: var(--bad); }
.rank-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-name small { display: block; color: var(--muted); font-size: 12px; }
.rank-value { text-align: right; font-weight: 700; white-space: nowrap; }
.ranking .empty { color: var(--muted); }
.calc-section { padding: 24px 0; border-top: 1px solid var(--line); }
.calc-head h2 { font-size: 17px; }
.calc-head span { font-size: 13px; }
.equation-scroll { overflow-x: auto; padding-bottom: 5px; }
.equation { display: flex; align-items: stretch; width: max-content; min-width: 100%; }
.term {
  width: 170px;
  min-height: 90px;
  padding: 11px 10px 10px;
  background: #fff;
  border-top: 3px solid #91a19b;
}
.term.refund { border-color: var(--bad); }
.term.cost { border-color: var(--warn); }
.term.result { width: 220px; background: #eef6f3; border-color: var(--brand); }
.term span { display: block; white-space: normal; }
.term b { display: block; margin-top: 10px; font-size: 21px; white-space: nowrap; }
.term small { display: block; margin-top: 3px; }
.operator {
  display: grid;
  width: 42px;
  min-width: 42px;
  place-items: center;
  color: #53615c;
  font-size: 25px;
  font-weight: 700;
}
.equation:not(.profit-equation) .term { width: 220px; }
.equation:not(.profit-equation) .term span { white-space: nowrap; }
.profit-equation { display: grid; width: 100%; min-width: 0;
  grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.profit-equation .term { width: auto; min-width: 0; padding: 14px 16px; }
.profit-equation .term.result, .profit-equation .term:nth-child(3) { grid-column: span 2; }
.profit-equation .term b { font-size: 21px; white-space: normal; overflow-wrap: anywhere; }
.profit-equation .operator { display: none; }
.profit-equation .term.cost span::before { content: "- "; color: var(--warn); }
.formula-note { margin: 0 0 12px; color: var(--muted); font-size: 13px; }
.controls { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px; margin: 0 0 16px; padding: 20px; background: var(--panel);
  border: 1px solid var(--line); border-radius: 8px; }
.controls label { display: flex; flex-direction: column; gap: 6px; min-width: 0; font-weight: 600; }
.controls input, .controls select {
  width: 100%; min-width: 0; height: 42px;
  padding: 0 12px; color: var(--ink); background: var(--panel); font-weight: 400;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.controls input::placeholder { color: var(--muted); opacity: 1; }
.filter-summary { display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 12px; color: var(--muted); }
.reset { border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 14px; background: var(--panel); cursor: pointer; }
.reset:hover { border-color: var(--brand); color: var(--brand); }
.empty-cell { padding: 40px 16px; text-align: left !important; color: var(--muted); }
.daily-chart-panel {
  margin-bottom: 12px;
  padding: 18px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.daily-chart-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 16px;
  margin-bottom: 8px;
}
.daily-chart-head h2 { margin: 0; font-size: 18px; }
.daily-chart-period { color: var(--muted); font-size: 12px; white-space: nowrap; }
.chart-controls {
  display: flex;
  gap: 3px;
  overflow-x: auto;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.chart-controls button {
  flex: none;
  padding: 9px 12px;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
  cursor: pointer;
  transition: color .16s, border-color .16s;
}
.chart-controls button:hover { color: var(--ink); }
.chart-controls button.active { color: var(--brand); border-color: var(--brand); font-weight: 700; }
.chart-controls button:focus-visible, .daily-chart-svg:focus-visible {
  outline: 2px solid var(--brand);
  outline-offset: 2px;
}
.daily-chart-svg { display: block; width: 100%; height: auto; aspect-ratio: 25 / 9; outline: none; }
.chart-axis-title { fill: var(--muted); font-size: 12px; }
.chart-axis-right-title { text-anchor: end; }
.chart-axis-label { fill: var(--muted); font-size: 11px; }
.chart-grid-line { stroke: #e7ecef; stroke-width: 1; }
.chart-zero-line { stroke: #7b8790; stroke-width: 1.3; stroke-dasharray: 4 4; }
.chart-line { fill: none; stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; }
.chart-bar { opacity: .76; }
.chart-point { fill: #fff; stroke-width: 2.5; }
.chart-focus-line { stroke: #7b8790; stroke-width: 1; stroke-dasharray: 3 4; pointer-events: none; }
.daily-chart-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 6px;
}
.chart-legend { display: flex; gap: 14px; flex-wrap: wrap; }
.chart-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--muted);
  font-size: 12px;
}
.chart-legend-item i {
  width: 9px;
  height: 9px;
  flex: none;
  background: var(--series-color);
  border-radius: 50%;
}
.daily-chart-readout {
  display: flex;
  min-height: 22px;
  align-items: baseline;
  gap: 12px;
  color: var(--ink);
  font-size: 12px;
  flex-wrap: wrap;
}
.daily-chart-readout > b { font-size: 12px; }
.daily-chart-readout > div { display: flex; gap: 12px; flex-wrap: wrap; }
.daily-chart-readout span { color: var(--muted); white-space: nowrap; }
.daily-chart-readout span::before {
  display: inline-block;
  width: 7px;
  height: 7px;
  margin-right: 5px;
  background: var(--series-color);
  border-radius: 50%;
  content: "";
}
.daily-chart-readout strong { color: var(--ink); font-weight: 700; }
.daily-chart-empty { padding: 90px 12px; color: var(--muted); text-align: center; }
.table-wrap {
  overflow: auto;
  max-height: 68vh;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
}
table { width: 100%; min-width: 1100px; border-collapse: collapse; }
th, td {
  padding: 12px 14px;
  border-bottom: 1px solid #edf0f2;
  text-align: right;
  white-space: nowrap;
}
th { position: sticky; top: 0; z-index: 1; color: #32463f; background: #eef3f1; }
tbody tr:nth-child(even) { background: #f7fafb; }
tbody tr:hover { background: var(--tint); }
th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align: left; }
td small { display: block; color: var(--muted); }
.tag { color: var(--brand); font-weight: 700; }
@media (min-width: 1280px) {
  main:has(#products:not([hidden])), main:has(#links:not([hidden])) {
    max-width: none;
    padding-right: 24px;
    padding-left: 24px;
  }
  #products table, #links table { min-width: 0; table-layout: fixed; }
  #products th, #products td, #links th, #links td {
    padding: 10px 5px;
    font-size: 12px;
    white-space: normal;
    overflow-wrap: anywhere;
    vertical-align: top;
  }
  #products th:first-child { width: 9%; }
  #products th:nth-child(n+15) { width: 3%; }
  #links th:first-child { width: 3%; }
  #links th:nth-child(2) { width: 5%; }
  #links th:nth-child(3) { width: 7%; }
  #links th:nth-child(4) { width: 11%; }
  #links th:last-child { width: 7%; }
  #links td:nth-child(3), #links td:nth-child(4), #links td:last-child {
    text-align: left;
  }
}
@media (min-width: 1920px) {
  #products th, #products td, #links th, #links td {
    padding: 12px 4px;
  }
}
footer {
  padding: 18px 28px;
  color: var(--muted);
  background: #fff;
  border-top: 1px solid var(--line);
}
@media (max-width: 1100px) {
  .ranking-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .key-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .key-metrics .metric { border-bottom: 1px solid var(--line); }
  .metrics, .controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
  header { align-items: start; flex-direction: column; padding: 14px 16px; }
  .meta { text-align: left; }
  nav, main { padding-right: 12px; padding-left: 12px; }
  nav { overflow: auto; }
  .metrics { grid-template-columns: 1fr 1fr; }
  .key-metrics, .controls { grid-template-columns: 1fr; }
  .key-metrics .metric { padding: 16px 20px; border-right: 0; }
  .controls { padding: 16px; }
  nav button { flex: none; padding: 12px; }
  .metric b { font-size: 20px; }
  .calc-head, .rankings-head { align-items: start; flex-direction: column; gap: 2px; }
  .ranking-grid { grid-template-columns: 1fr; }
  .equation { width: 100%; min-width: 0; flex-direction: column; }
  .term, .term.result, .equation:not(.profit-equation) .term,
  .profit-equation .term, .profit-equation .term.result { width: 100%; }
  .profit-equation { grid-template-columns: 1fr; }
  .profit-equation .term.result, .profit-equation .term:nth-child(3) { grid-column: auto; }
  .equation:not(.profit-equation) .term span { white-space: normal; }
  .operator, .profit-equation .operator { width: 100%; height: 30px; min-height: 30px; }
  .daily-chart-panel { padding: 12px; }
  .daily-chart-head { align-items: start; flex-direction: column; gap: 3px; }
  .daily-chart-period { white-space: normal; }
  .chart-controls { margin-right: -12px; }
  .chart-controls button { padding: 9px 10px; }
  .daily-chart-svg { min-height: 210px; }
  .daily-chart-bottom { align-items: flex-start; flex-direction: column; }
}
@media (prefers-reduced-motion: reduce) {
  .chart-controls button { transition: none; }
}
"""

REPORT_SCRIPT = r"""
const DATA = __REPORT_DATA__;
const profitTitle = __PROFIT_TITLE__;
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[char]));
const money = value => value == null ? '--' : '¥' + (value / 100).toLocaleString('zh-CN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});
const pct = value => value == null ? '暂无比例' : (value * 100).toFixed(2) + '%';
const num = value => value == null ? '--' : Number(value).toLocaleString('zh-CN');
const roi = value => value == null ? '--' : Number(value).toFixed(2) + 'x';

document.querySelectorAll('nav button').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('nav button').forEach(item => {
      item.classList.toggle('active', item === button);
      item.setAttribute('aria-pressed', String(item === button));
    });
    document.querySelectorAll('.view').forEach(view => {
      view.hidden = view.id !== button.dataset.view;
    });
  });
});

const S = DATA.summary;
const accounted = S['已核算销售额_分'] || 0;
const accountedRefund = S['已核算订单批次成功退款_分'] || 0;
const accountedNet = accounted - accountedRefund;
const term = (label, value, tone = '', note = '') =>
  `<div class="term ${tone}"><span>${label}</span>` +
  `<b class="${value < 0 ? 'negative' : ''}">${money(value)}</b>` +
  `${note ? `<small>${note}</small>` : ''}</div>`;
const op = value => `<div class="operator" aria-hidden="true">${value}</div>`;
const paid = S['已付款销售额_分'] || 0;
const brush = S['刷单金额_分'] || 0;
const allRefund = S['订单批次成功退款金额_分'] || 0;
const realSales = S['真实销售额_分'] || 0;
const share = (value, base) => pct(base ? value / base : null);
const keyMetrics = [
  ['真实销售额', money(S['真实销售额_分']), '扣除刷单金额与订单批次退款'],
  [profitTitle, money(S['含推广经营贡献利润_分']), '已扣除推广花费'],
  ['经营贡献利润率', pct(S['经营贡献利润率']), '已核算部分口径'],
  ['销售额核算覆盖率', pct(S['销售额核算覆盖率']), '衡量成本与运费核算完整性']
];
document.querySelector('#keyMetrics').innerHTML = keyMetrics.map((item, index) =>
  `<div class="metric${index === 1 ? ' primary' : ''}"><span>${item[0]}</span>` +
  `<b class="${(index === 1 && S['含推广经营贡献利润_分'] < 0) ||
    (index === 2 && S['经营贡献利润率'] < 0) ? 'negative' : ''}">${item[1]}</b>` +
  `<small>${item[2]}</small></div>`
).join('');

document.querySelector('#salesEquation').innerHTML =
  term('真实销售额', realSales, 'result', `占已付款销售额 ${share(realSales, paid)}`) +
  op('=') + term('已付款销售额', paid, '', `销售基准 ${pct(paid ? 1 : null)}`) +
  op('−') + term('刷单金额', brush, 'cost', `占已付款销售额 ${share(brush, paid)}`) +
  op('−') + term('全部订单批次成功退款', allRefund, 'refund', `退款率 ${share(allRefund, paid)}`);
document.querySelector('#accountedEquation').innerHTML =
  term('已核算净销售额', accountedNet, 'result',
    `占已核算销售额 ${share(accountedNet, accounted)}`) +
  op('=') + term('已核算销售额', accounted, '', `占已付款销售额 ${share(accounted, paid)}`) +
  op('−') + term('已核算订单批次成功退款', accountedRefund, 'refund',
    `占已核算销售额 ${share(accountedRefund, accounted)}`);
document.querySelector('#profitEquation').innerHTML =
  term(profitTitle, S['含推广经营贡献利润_分'], 'result', `利润率 ${pct(S['经营贡献利润率'])}`) +
  op('=') +
  term('已核算净销售额', accountedNet, '',
    `净销售额基准 ${pct(accountedNet ? 1 : null)}`) +
  op('−') + term('货品成本', S['已核算货品成本_分'], 'cost',
    `占净销售额 ${share(S['已核算货品成本_分'], accountedNet)}`) +
  op('−') + term('运费', S['已核算运费_分'], 'cost',
    `占净销售额 ${share(S['已核算运费_分'], accountedNet)}`) +
  op('−') + term('刷单成本', S['已核算刷单成本_分'], 'cost',
    `等于刷单金额 ${money(S['刷单金额_分'])}`) +
  op('−') + term('平台扣点（估算）', S['已核算平台扣点_分'], 'cost',
    `占净销售额 ${share(S['已核算平台扣点_分'], accountedNet)}`) +
  op('−') + term('综合税赋（估算）', S['已核算综合税赋_分'], 'cost',
    `占净销售额 ${share(S['已核算综合税赋_分'], accountedNet)}`) +
  op('−') + term('关闭已发货损失', S['关闭已发货损失_分'], 'cost',
    `占净销售额 ${share(S['关闭已发货损失_分'], accountedNet)}`) +
  op('−') + term('推广花费', S['推广花费_分'], 'cost',
    `占净销售额 ${share(S['推广花费_分'], accountedNet)}`);
document.querySelector('#accountingCoverage').textContent =
  `销售额核算覆盖率 ${pct(S['销售额核算覆盖率'])}`;

const cards = [
  ['刷单金额', brush, '刷单成本同金额计入利润', 'money'],
  ['期间退款完结金额', S['期间退款完结金额_分'], '退款完结日期口径', 'money'],
  ['推广花费', S['推广花费_分'],
    `占已核算净销售额 ${pct(accountedNet ? S['推广花费_分'] / accountedNet : null)}`, 'money'],
  ['推广归因成交金额', S['推广归因成交金额_分'], `推广投产比 ${roi(S['推广投产比'])}`, 'money'],
  ['退款订单率', S['退款订单率'], '主订单口径', 'ratio'],
  ['付款后关闭率', S['付款后关闭率'], '主订单口径', 'ratio'],
  ['关闭已发货率', S['关闭已发货率'], '主订单口径', 'ratio']
];
document.querySelector('#summaryMetrics').innerHTML = cards.map(card =>
  `<div class="metric"><span>${card[0]}</span>` +
  `<b class="${card[1] < 0 ? 'negative' : ''}">` +
  `${card[3] === 'ratio' ? pct(card[1]) : money(card[1])}</b>` +
  `<small>${card[2]}</small></div>`
).join('');

const topRows = (rows, key, filter = () => true, ascending = false) =>
  rows.filter(filter)
    .sort((a, b) => (Number(a[key] ?? 0) - Number(b[key] ?? 0)) * (ascending ? 1 : -1))
    .slice(0, 10);
const rank = (title, rows, name, value, note, risk = false) => {
  const content = rows.length
    ? `<ol>${rows.map(row =>
      `<li><span class="rank-name" title="${esc(name(row))}">` +
      `${esc(name(row))}<small>${note(row)}</small></span>` +
      `<span class="rank-value${risk ? ' negative' : ''}">${value(row)}</span></li>`
    ).join('')}</ol>`
    : '<div class="empty">暂无符合口径的数据</div>';
  return `<section class="ranking${risk ? ' risk' : ''}"><h3>${title}</h3>${content}</section>`;
};
const productName = row => row['产品名称'] || '未归类';
const linkName = row => row['商品标题'] || row['商品ID'] || '未命名链接';
const roiSpendFloor = Math.max(10000, Number(S['推广花费_分'] || 0) * 0.01);
const rankingGroups = [
  rank('产品销售榜', topRows(DATA.products, '销售额_分'), productName,
    row => money(row['销售额_分']), row => `贡献 ${pct(row['销售贡献率'])}`),
  rank('产品退款榜', topRows(DATA.products, '订单批次成功退款_分',
    row => Number(row['订单批次成功退款_分'] || 0) > 0), productName,
    row => money(row['订单批次成功退款_分']), row => `退款率 ${pct(row['退款率'])}`, true),
  rank('产品利润榜', topRows(DATA.products, '含推广经营贡献利润_分',
    row => row['经营贡献利润率状态'] === '已核算' &&
      Number(row['含推广经营贡献利润_分'] || 0) > 0), productName,
    row => money(row['含推广经营贡献利润_分']),
    row => `利润率 ${pct(row['经营贡献利润率'])}`),
  rank('热销产品榜', topRows(DATA.sku, '销售额_分',
    row => Number(row['销售额_分'] || 0) > 0),
    row => row['商家编码'] || '无商家编码', row => money(row['销售额_分']),
    row => `销售占比 ${pct(paid ? Number(row['销售额_分'] || 0) / paid : null)}`),
  rank('链接销售榜', topRows(DATA.links, '销售额_分',
    row => Number(row['销售额_分'] || 0) > 0), linkName,
    row => money(row['销售额_分']), row => `贡献 ${pct(row['销售贡献率'])}`),
  rank('链接退款榜', topRows(DATA.links, '订单批次成功退款_分',
    row => Number(row['订单批次成功退款_分'] || 0) > 0), linkName,
    row => money(row['订单批次成功退款_分']), row => `退款率 ${pct(row['退款率'])}`, true),
  rank('链接花费榜', topRows(DATA.links, '推广花费_分',
    row => Number(row['推广花费_分'] || 0) > 0), linkName,
    row => money(row['推广花费_分']), row => `投产 ${roi(row['推广投产比'])}`),
  rank('链接利润榜', topRows(DATA.links, '含推广经营贡献利润_分',
    row => row['核算状态'] === '已核算' &&
      Number(row['含推广经营贡献利润_分'] || 0) > 0), linkName,
    row => money(row['含推广经营贡献利润_分']),
    row => `利润率 ${pct(row['经营贡献利润率'])}`),
  rank(`链接投产榜 · 花费≥${money(roiSpendFloor)}`,
    topRows(DATA.links, '推广投产比',
      row => Number(row['推广花费_分'] || 0) >= roiSpendFloor), linkName,
    row => roi(row['推广投产比']), row => `花费 ${money(row['推广花费_分'])}`),
  rank('链接亏损预警', topRows(DATA.links, '含推广经营贡献利润_分',
    row => row['核算状态'] === '已核算' &&
      Number(row['含推广经营贡献利润_分'] || 0) < 0, true), linkName,
    row => money(row['含推广经营贡献利润_分']),
    row => `亏损占比 ${pct(row['亏损占比'])}`, true)
];
document.querySelector('#rankings').innerHTML = rankingGroups.join('');

const dailyCharts = {
  sales: {
    title: '销售表现',
    axis: '金额（元）',
    series: [
      { key: '销售额_分', label: '销售额', color: '#176b54', format: 'money' },
      { key: '真实销售额_分', label: '真实销售额', color: '#3a7695', format: 'money' },
      { key: '刷单金额_分', label: '刷单金额', color: '#a65d00', format: 'money' }
    ]
  },
  profit: {
    title: '经营利润',
    axis: '金额（元）',
    series: [
      { key: '含推广经营贡献利润_分', label: '经营贡献利润', color: '#176b54', format: 'money' },
      { key: '关闭已发货损失_分', label: '关闭已发货损失', color: '#b42318', format: 'money' }
    ]
  },
  promotion: {
    title: '推广表现',
    axis: '金额（元）',
    series: [
      { key: '推广花费_分', label: '推广花费', color: '#a65d00', format: 'money' },
      { key: '推广归因成交金额_分', label: '推广归因成交', color: '#3a7695', format: 'money' }
    ]
  },
  orders: {
    title: '订单与退款',
    axis: '订单（单）',
    rightAxis: '退款金额（元）',
    series: [
      {
        key: '已付款主订单数', label: '已付款主订单数', color: '#176b54',
        format: 'number', type: 'bar'
      },
      {
        key: '订单批次成功退款_分', label: '订单批次退款', color: '#b42318',
        format: 'money', axis: 'right'
      },
      {
        key: '期间退款完结金额_分', label: '期间退款完结', color: '#75828a',
        format: 'money', axis: 'right'
      }
    ]
  }
};
const chartNode = document.querySelector('#dailyChart');
const chartEmpty = document.querySelector('#dailyChartEmpty');
const chartLegend = document.querySelector('#dailyChartLegend');
const chartReadout = document.querySelector('#dailyChartReadout');
const chartTitle = document.querySelector('#dailyChartTitle');
const chartPeriod = document.querySelector('#dailyChartPeriod');
const dailyRows = [...DATA.daily].sort((a, b) =>
  String(a['日期'] || '').localeCompare(String(b['日期'] || ''))
);
const chartNumber = (row, key) => {
  const raw = row[key];
  if (raw == null || raw === '') return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
};
const chartDomain = series => {
  const values = dailyRows
    .flatMap(row => series.map(item => chartNumber(row, item.key)))
    .filter(value => value != null);
  if (!values.length) return { min: 0, max: 1 };
  let min = Math.min(0, ...values);
  let max = Math.max(0, ...values);
  if (min === max) max = 1;
  const span = max - min;
  if (min < 0) min -= span * 0.08;
  max += span * 0.12;
  return { min, max };
};
const chartTick = (value, format) => {
  if (format !== 'money') {
    return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(value);
  }
  const compact = new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1
  }).format(value / 100);
  return '¥' + compact;
};
const chartValue = (value, format) => value == null ? '--'
  : format === 'money' ? money(value) : num(value);
let activeChart = 'sales';
let activeDailyIndex = -1;
const showDailyPoint = index => {
  if (index < 0 || index >= dailyRows.length || index === activeDailyIndex) return;
  activeDailyIndex = index;
  const row = dailyRows[index];
  const values = dailyCharts[activeChart].series.map(series =>
    `<span style="--series-color:${series.color}">${esc(series.label)} ` +
    `<strong>${chartValue(chartNumber(row, series.key), series.format)}</strong></span>`
  ).join('');
  chartReadout.innerHTML = `<b>${esc(row['日期'] || '--')}</b><div>${values}</div>`;
  const focusLine = chartNode.querySelector('.chart-focus-line');
  if (!focusLine) return;
  const plotStart = Number(chartNode.dataset.plotStart);
  const plotWidth = Number(chartNode.dataset.plotWidth);
  const x = plotStart + (dailyRows.length === 1
    ? plotWidth / 2
    : plotWidth * index / (dailyRows.length - 1));
  focusLine.setAttribute('x1', x);
  focusLine.setAttribute('x2', x);
  focusLine.setAttribute('visibility', 'visible');
};
const renderDailyChart = key => {
  activeChart = key;
  activeDailyIndex = -1;
  const config = dailyCharts[key];
  chartTitle.textContent = config.title;
  document.querySelectorAll('[data-daily-chart]').forEach(button => {
    const selected = button.dataset.dailyChart === key;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  if (!dailyRows.length) {
    chartNode.style.display = 'none';
    chartEmpty.hidden = false;
    chartLegend.innerHTML = '';
    chartReadout.textContent = '暂无每日数据';
    chartPeriod.textContent = '暂无数据';
    return;
  }
  chartNode.style.display = '';
  chartEmpty.hidden = true;
  chartPeriod.textContent =
    `${dailyRows[0]['日期']} 至 ${dailyRows[dailyRows.length - 1]['日期']} · ` +
    `${dailyRows.length} 天`;
  const width = 1000;
  const height = 360;
  const margin = { top: 34, right: config.rightAxis ? 86 : 30, bottom: 50, left: 88 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const plotBottom = margin.top + plotHeight;
  const leftSeries = config.series.filter(series => series.axis !== 'right');
  const rightSeries = config.series.filter(series => series.axis === 'right');
  const leftDomain = chartDomain(leftSeries);
  const rightDomain = rightSeries.length ? chartDomain(rightSeries) : null;
  const y = (value, axis) => {
    const domain = axis === 'right' ? rightDomain : leftDomain;
    return plotBottom - (value - domain.min) / (domain.max - domain.min) * plotHeight;
  };
  const x = index => margin.left + (dailyRows.length === 1
    ? plotWidth / 2
    : plotWidth * index / (dailyRows.length - 1));
  const parts = [
    `<title id="dailyChartSvgTitle">${esc(config.title)}</title>`,
    `<desc id="dailyChartSvgDesc">` +
      `${esc(config.series.map(series => series.label).join('、'))}每日趋势</desc>`,
    `<text class="chart-axis-title" x="${margin.left}" y="18">${esc(config.axis)}</text>`
  ];
  if (config.rightAxis) {
    parts.push(
      `<text class="chart-axis-title chart-axis-right-title" ` +
      `x="${width - margin.right}" y="18">${esc(config.rightAxis)}</text>`
    );
  }
  for (let tick = 0; tick <= 4; tick++) {
    const value = leftDomain.max - (leftDomain.max - leftDomain.min) * tick / 4;
    const yPosition = margin.top + plotHeight * tick / 4;
    parts.push(
      `<line class="chart-grid-line" x1="${margin.left}" y1="${yPosition}" ` +
      `x2="${width - margin.right}" y2="${yPosition}"/>`
    );
    parts.push(
      `<text class="chart-axis-label" x="${margin.left - 12}" ` +
      `y="${yPosition + 4}" text-anchor="end">` +
      `${esc(chartTick(value, leftSeries[0]?.format))}</text>`
    );
    if (rightDomain) {
      const rightValue = rightDomain.max - (rightDomain.max - rightDomain.min) * tick / 4;
      parts.push(
        `<text class="chart-axis-label" x="${width - margin.right + 12}" ` +
        `y="${yPosition + 4}">${esc(chartTick(rightValue, rightSeries[0]?.format))}</text>`
      );
    }
  }
  if (leftDomain.min < 0 && leftDomain.max > 0) {
    parts.push(
      `<line class="chart-zero-line" x1="${margin.left}" ` +
      `y1="${y(0, 'left')}" x2="${width - margin.right}" ` +
      `y2="${y(0, 'left')}"/>`
    );
  }
  const labelStep = Math.max(1, Math.ceil((dailyRows.length - 1) / 7));
  dailyRows.forEach((row, index) => {
    if (index % labelStep !== 0 && index !== dailyRows.length - 1) return;
    const date = String(row['日期'] || '');
    const label = date.length >= 10 ? date.slice(5, 10) : date;
    parts.push(
      `<text class="chart-axis-label chart-date-label" x="${x(index)}" ` +
      `y="${height - 16}" text-anchor="middle">${esc(label)}</text>`
    );
  });
  config.series.forEach(series => {
    const axis = series.axis || 'left';
    const values = dailyRows.map(row => chartNumber(row, series.key));
    if (series.type === 'bar') {
      const barWidth = Math.min(26, Math.max(5, plotWidth / dailyRows.length * 0.54));
      values.forEach((value, index) => {
        if (value == null) return;
        const zeroY = y(0, axis);
        const valueY = y(value, axis);
        const rectY = Math.min(zeroY, valueY);
        const rectHeight = Math.max(1, Math.abs(zeroY - valueY));
        parts.push(
          `<rect class="chart-bar" fill="${series.color}" x="${x(index) - barWidth / 2}" ` +
          `y="${rectY}" width="${barWidth}" height="${rectHeight}" rx="3"/>`
        );
      });
      return;
    }
    let segment = [];
    const flush = () => {
      if (segment.length > 1) {
        const path = segment.map((point, index) =>
          `${index ? 'L' : 'M'}${point.x.toFixed(2)},${point.y.toFixed(2)}`
        ).join(' ');
        parts.push(
          `<path class="chart-line" stroke="${series.color}" d="${path}"/>`
        );
      } else if (segment.length === 1) {
        const point = segment[0];
        parts.push(
          `<circle class="chart-point" stroke="${series.color}" ` +
          `cx="${point.x}" cy="${point.y}" r="3.5"/>`
        );
      }
      segment = [];
    };
    values.forEach((value, index) => {
      if (value == null) {
        flush();
        return;
      }
      segment.push({ x: x(index), y: y(value, axis) });
    });
    flush();
  });
  parts.push(
    `<line class="chart-focus-line" x1="${x(0)}" y1="${margin.top}" ` +
    `x2="${x(0)}" y2="${plotBottom}" visibility="hidden"/>`
  );
  chartNode.innerHTML = parts.join('');
  chartNode.dataset.plotStart = String(margin.left);
  chartNode.dataset.plotWidth = String(plotWidth);
  chartLegend.innerHTML = config.series.map(series =>
    `<span class="chart-legend-item">` +
    `<i style="--series-color:${series.color}"></i>${esc(series.label)}</span>`
  ).join('');
  chartNode.setAttribute('aria-label', `${config.title}，使用左右方向键查看每日数据`);
  showDailyPoint(dailyRows.length - 1);
};
document.querySelectorAll('[data-daily-chart]').forEach(button => {
  button.addEventListener('click', () => renderDailyChart(button.dataset.dailyChart));
});
chartNode.addEventListener('pointermove', event => {
  if (!dailyRows.length) return;
  const bounds = chartNode.getBoundingClientRect();
  const chartX = (event.clientX - bounds.left) / bounds.width * 1000;
  const start = Number(chartNode.dataset.plotStart);
  const width = Number(chartNode.dataset.plotWidth);
  const ratio = Math.max(0, Math.min(1, (chartX - start) / width));
  const index = dailyRows.length === 1 ? 0 : Math.round(ratio * (dailyRows.length - 1));
  showDailyPoint(index);
});
chartNode.addEventListener('click', event => {
  const bounds = chartNode.getBoundingClientRect();
  const chartX = (event.clientX - bounds.left) / bounds.width * 1000;
  const start = Number(chartNode.dataset.plotStart);
  const width = Number(chartNode.dataset.plotWidth);
  const ratio = Math.max(0, Math.min(1, (chartX - start) / width));
  const index = dailyRows.length === 1 ? 0 : Math.round(ratio * (dailyRows.length - 1));
  showDailyPoint(index);
});
chartNode.addEventListener('keydown', event => {
  if (!dailyRows.length) return;
  let index = activeDailyIndex < 0 ? dailyRows.length - 1 : activeDailyIndex;
  if (event.key === 'ArrowLeft') index = Math.max(0, index - 1);
  else if (event.key === 'ArrowRight') index = Math.min(dailyRows.length - 1, index + 1);
  else if (event.key === 'Home') index = 0;
  else if (event.key === 'End') index = dailyRows.length - 1;
  else return;
  event.preventDefault();
  showDailyPoint(index);
});
renderDailyChart('sales');

function table(element, rows, columns) {
  const node = document.querySelector(element);
  const head = '<thead><tr>' +
    columns.map(column => `<th>${column[0]}</th>`).join('') +
    '</tr></thead>';
  const body = rows.map(row => '<tr>' + columns.map(column => {
    const value = column[2]
      ? column[2](row[column[1]], row)
      : esc(row[column[1]] ?? '--');
    return `<td>${value}</td>`;
  }).join('') + '</tr>').join('');
  const emptyText = element === '#dailyTable' ? '本期暂无每日数据' : '本期暂无产品数据';
  node.innerHTML = head + `<tbody>${body ||
    `<tr><td class="empty-cell" colspan="${columns.length}">${emptyText}</td></tr>`}</tbody>`;
}
const M = value => money(value);
const P = value => pct(value);
const N = value => num(value);
const R = value => roi(value);
table('#dailyTable', DATA.daily, [
  ['日期', '日期'], ['主订单数', '已付款主订单数', N], ['购买数量', '购买数量', N],
  ['销售额', '销售额_分', M], ['刷单金额', '刷单金额_分', M],
  ['真实销售额', '真实销售额_分', M], ['占期间销售', '占期间销售比例', P],
  ['订单批次退款', '订单批次成功退款_分', M], ['期间退款完结', '期间退款完结金额_分', M],
  ['成本', '货品成本_分', M], ['运费', '运费_分', M], ['刷单成本', '刷单成本_分', M],
  ['平台费率', '平台费率', P], ['税费率', '税费率', P], ['推广花费', '推广花费_分', M],
  ['推广费率', '推广费率', P], ['推广投产比', '推广投产比', R],
  ['经营贡献利润', '含推广经营贡献利润_分', M], ['利润率', '经营贡献利润率', P],
  ['核算覆盖率', '核算覆盖率', P]
]);
const productMargin = (value, row) => row['经营贡献利润率状态'] === '已核算'
  ? P(value) : esc(row['经营贡献利润率状态']);
table('#productTable', DATA.products, [
  ['产品名称', '产品名称'], ['SKU数', 'SKU数', N], ['链接数', '商品链接数', N],
  ['主订单数', '已付款主订单数', N], ['销售额', '销售额_分', M],
  ['刷单金额', '刷单金额_分', M], ['真实销售额', '真实销售额_分', M],
  ['净销售额', '净销售额_分', M], ['销售贡献率', '销售贡献率', P],
  ['订单批次退款', '订单批次成功退款_分', M], ['推广花费', '推广花费_分', M],
  ['推广投产比', '推广投产比', R], ['经营贡献利润', '含推广经营贡献利润_分', M],
  ['利润率', '经营贡献利润率', productMargin], ['S', 'S链接数', N], ['A', 'A链接数', N],
  ['B', 'B链接数', N], ['C', 'C链接数', N], ['待核算', '待核算链接数', N]
]);

const columns = [
  ['SABC', 'SABC等级'], ['产品', '产品名称'], ['商品ID', '商品ID'],
  ['商品标题', '商品标题'], ['覆盖', '数据覆盖'], ['核算', '核算状态'],
  ['销售额', '销售额_分', M], ['刷单金额', '刷单金额_分', M],
  ['真实销售额', '真实销售额_分', M], ['销售贡献率', '销售贡献率', P],
  ['退款', '订单批次成功退款_分', M], ['退款率', '退款率', P],
  ['成本', '货品成本_分', M], ['运费', '运费_分', M], ['刷单成本', '刷单成本_分', M],
  ['推广花费', '推广花费_分', M], ['推广投产比', '推广投产比', R],
  ['经营贡献利润', '含推广经营贡献利润_分', M], ['利润率', '经营贡献利润率', P],
  ['盈利贡献/亏损占比', '盈利贡献率', P], ['运营动作', '运营动作']
];
document.querySelector('#linkHead').innerHTML =
  '<tr>' + columns.map(column => `<th>${column[0]}</th>`).join('') + '</tr>';
const controls = ['search', 'productFilter', 'sabc', 'profit', 'coverage', 'accounting', 'sort']
  .map(id => document.querySelector('#' + id));
for (const [id, key] of [['productFilter', '产品名称'], ['sabc', 'SABC等级']]) {
  const select = document.querySelector('#' + id);
  [...new Set(DATA.links.map(row => row[key]).filter(Boolean))].sort().forEach(value => {
    select.add(new Option(value, value));
  });
}
function renderLinks() {
  let rows = DATA.links.filter(row => {
    const searchable = `${row['商品ID']} ${row['商品标题']}`.toLowerCase();
    return (!controls[0].value || searchable.includes(controls[0].value.toLowerCase())) &&
      (!controls[1].value || row['产品名称'] === controls[1].value) &&
      (!controls[2].value || row['SABC等级'] === controls[2].value) &&
      (!controls[3].value || row['盈利状态'] === controls[3].value) &&
      (!controls[4].value || row['数据覆盖'] === controls[4].value) &&
      (!controls[5].value || row['核算状态'] === controls[5].value);
  });
  const sorts = {
    profitDesc: ['含推广经营贡献利润_分', -1],
    salesDesc: ['销售额_分', -1],
    marginDesc: ['经营贡献利润率', -1],
    spendDesc: ['推广花费_分', -1],
    roiDesc: ['推广投产比', -1],
    refundDesc: ['退款率', -1]
  };
  const [key, direction] = sorts[controls[6].value];
  rows.sort((a, b) => ((a[key] ?? -Infinity) - (b[key] ?? -Infinity)) * direction);
  document.querySelector('#linkCount').textContent =
    `匹配 ${rows.length} / ${DATA.links.length} 个链接`;
  document.querySelector('#rows').innerHTML = rows.map(row => '<tr>' +
    columns.map(column => {
      let value = column[2]
        ? column[2](row[column[1]], row)
        : esc(row[column[1]] ?? '--');
      if (column[1] === '盈利贡献率' && row['亏损占比'] != null) {
        value = P(row['亏损占比']);
      }
      const negative = row['含推广经营贡献利润_分'] < 0 &&
        column[1] === '含推广经营贡献利润_分';
      return `<td class="${negative ? 'negative' : ''}">${value}</td>`;
    }).join('') + '</tr>').join('') ||
    `<tr><td class="empty-cell" colspan="${columns.length}">` +
    '没有匹配的链接，请调整或重置筛选条件。</td></tr>';
}
controls.forEach(control => control.addEventListener('input', renderLinks));
document.querySelector('#resetFilters').addEventListener('click', () => {
  controls.forEach(control => { control.value = control.id === 'sort' ? 'profitDesc' : ''; });
  renderLinks();
});
renderLinks();
"""


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
    return [
        {str(key): _json_value(value) for key, value in row.items()}
        for row in frame.to_dict("records")
    ]


def _json_for_script(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def write_html(result: Any, config: RunConfig, path: Path) -> None:
    analysis = result.analysis
    summary = analysis.summary
    payload = {
        "summary": {key: _json_value(value) for key, value in summary.items()},
        "daily": _records(analysis.daily),
        "products": _records(analysis.products),
        "links": _records(analysis.links),
        "sku": _records(analysis.sku),
    }
    data = _json_for_script(payload)
    status = html.escape(result.reconciliation.status.value)
    profit_title = "已核算部分经营贡献利润" if status == "PROVISIONAL" else "含推广经营贡献利润"
    status_label = "待补成本 / 运费" if status == "PROVISIONAL" else "核算完整"
    notice = (
        '<div class="notice" role="note">成本或运费尚未补齐，利润仅反映已核算部分，'
        '不得作为最终利润。请补齐待补清单后重新生成报告。</div>'
        if status == "PROVISIONAL" else ""
    )
    script = REPORT_SCRIPT.replace("__REPORT_DATA__", data).replace(
        "__PROFIT_TITLE__", _json_for_script(profit_title)
    )
    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>店铺经营复盘</title>
  <style>
{REPORT_CSS}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>店铺经营复盘</h1>
      <div class="period">{config.start_date.isoformat()} 至 {config.end_date.isoformat()}</div>
    </div>
    <div class="meta">
      <b class="status {status.lower()}">{status} · {status_label}</b><br>
      {html.escape(config.platform.value)}　平台费 {config.platform_fee_rate:.2%}
     　税赋 {config.tax_rate:.2%}
    </div>
  </header>
  <nav aria-label="报告视图">
    <button class="active" data-view="overview" aria-controls="overview"
      aria-pressed="true">经营总览</button>
    <button data-view="daily" aria-controls="daily" aria-pressed="false">每日经营</button>
    <button data-view="products" aria-controls="products" aria-pressed="false">产品分析</button>
    <button data-view="links" aria-controls="links" aria-pressed="false">链接分析</button>
  </nav>
  <main>
    {notice}
    <section id="overview" class="view">
      <div class="key-metrics" id="keyMetrics" aria-label="核心经营指标"></div>
      <div class="calc-section">
        <div class="calc-head">
          <h2>全部订单销售链</h2><span>按订单付款日期归属</span>
        </div>
        <div class="equation-scroll"><div class="equation" id="salesEquation"></div></div>
      </div>
      <div class="calc-section">
        <div class="calc-head">
          <h2>已核算利润链</h2><span id="accountingCoverage"></span>
        </div>
        <div class="equation-scroll">
          <div class="equation" id="accountedEquation"></div>
        </div>
        <p class="formula-note">经营贡献利润 = 已核算净销售额 - 以下各项成本与费用</p>
        <div class="equation profit-equation" id="profitEquation"></div>
      </div>
      <div class="metrics" id="summaryMetrics"></div>
      <section class="rankings">
        <div class="rankings-head">
          <h2>运营榜单</h2>
          <span>产品看规模与退款，链接看利润、投产与风险</span>
        </div>
        <div class="ranking-grid" id="rankings"></div>
      </section>
    </section>
    <section id="daily" class="view" hidden>
      <section class="daily-chart-panel" aria-labelledby="dailyChartTitle">
        <div class="daily-chart-head">
          <h2 id="dailyChartTitle">销售表现</h2>
          <span class="daily-chart-period" id="dailyChartPeriod"></span>
        </div>
        <div class="chart-controls" role="group" aria-label="每日趋势指标">
          <button type="button" class="active" data-daily-chart="sales" aria-pressed="true">
            销售
          </button>
          <button type="button" data-daily-chart="profit" aria-pressed="false">利润</button>
          <button type="button" data-daily-chart="promotion" aria-pressed="false">推广</button>
          <button type="button" data-daily-chart="orders" aria-pressed="false">
            订单与退款
          </button>
        </div>
        <svg id="dailyChart" class="daily-chart-svg" viewBox="0 0 1000 360" role="img"
          tabindex="0" aria-label="每日销售趋势图，使用左右方向键查看数据"></svg>
        <div id="dailyChartEmpty" class="daily-chart-empty" hidden>本期暂无每日数据</div>
        <div class="daily-chart-bottom">
          <div id="dailyChartLegend" class="chart-legend" aria-hidden="true"></div>
          <div id="dailyChartReadout" class="daily-chart-readout" role="status"
            aria-live="polite"></div>
        </div>
      </section>
      <div class="table-wrap"><table id="dailyTable"></table></div>
    </section>
    <section id="products" class="view" hidden>
      <div class="view-heading"><h2>产品分析</h2><p>对比产品销售规模、退款与经营贡献利润。</p></div>
      <div class="table-wrap"><table id="productTable"></table></div>
    </section>
    <section id="links" class="view" hidden>
      <div class="view-heading"><h2>链接分析</h2>
        <p>筛选问题链接，结合核算状态与运营动作复核。</p></div>
      <div class="controls">
        <label for="search">商品搜索
          <input id="search" type="search" placeholder="商品ID或标题"></label>
        <label for="productFilter">产品
          <select id="productFilter"><option value="">全部产品</option></select></label>
        <label for="sabc">SABC等级
          <select id="sabc"><option value="">全部 SABC</option></select></label>
        <label for="profit">盈亏状态<select id="profit">
          <option value="">全部盈亏</option><option>盈利</option><option>亏损</option>
          <option>持平</option><option>待核算</option>
        </select></label>
        <label for="coverage">数据覆盖<select id="coverage">
          <option value="">全部覆盖</option><option>订单+推广</option><option>仅订单</option>
          <option>仅推广</option>
        </select></label>
        <label for="accounting">核算状态<select id="accounting">
          <option value="">全部核算状态</option><option>已核算</option>
          <option>成本或运费缺失</option>
        </select></label>
        <label for="sort">排序方式<select id="sort">
          <option value="profitDesc">经营贡献利润：高到低</option>
          <option value="salesDesc">销售额：高到低</option>
          <option value="marginDesc">经营贡献利润率：高到低</option>
          <option value="spendDesc">推广花费：高到低</option>
          <option value="roiDesc">推广投产比：高到低</option>
          <option value="refundDesc">退款率：高到低</option>
        </select></label>
      </div>
      <div class="filter-summary"><span id="linkCount" role="status" aria-live="polite"></span>
        <button id="resetFilters" class="reset" type="button">重置筛选</button></div>
      <div class="table-wrap">
        <table><thead id="linkHead"></thead><tbody id="rows"></tbody></table>
      </div>
    </section>
  </main>
  <footer>
    推广归因成交金额不计入订单销售额。
    平台扣点与综合税赋为管理估算值。产品推广数据为链接级分摊估算。
    SABC 阈值：{config.s_profit_share:.0%}/{config.a_profit_share:.0%}；
    配置：{html.escape(str(config.sabc_config or "默认"))}。
  </footer>
  <script>{script}</script>
</body>
</html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8", newline="\n")
