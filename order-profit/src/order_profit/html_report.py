"""面向运营复盘的自包含 HTML 报告。"""

from __future__ import annotations

import html
import json
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from order_profit import __version__
from order_profit.config import RunConfig

if TYPE_CHECKING:
    from order_profit.pipeline import ValidationResult


def _money(cents: int | Any) -> str:
    return f"¥{int(cents) / 100:,.2f}"


def _percent(value: Decimal | Any) -> str:
    return f"{float(value) * 100:.2f}%"


def _safe(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _json_for_script(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _link_rows(result: ValidationResult) -> list[dict[str, Any]]:
    rows = []
    for _, row in result.analysis.links.iterrows():
        rows.append(
            {
                "id": str(row["商品ID"]),
                "url": str(row["商品链接"]),
                "title": str(row["商品标题"]),
                "coverage": str(row["数据覆盖"]),
                "accounting": str(row["核算状态"]),
                "profitState": str(row["盈利状态"]),
                "orders": int(row["正常订单行数"]),
                "sales": int(row["全部销售额_分"]),
                "refund": int(row["全部有效退款_分"]),
                "cost": int(row["正常订单货品成本_分"]),
                "freight": int(row["正常订单运费_分"]),
                "platformFee": int(row["平台扣点_分"]),
                "tax": int(row["综合税赋_分"]),
                "closedLoss": int(row["关闭已发货损失_分"]),
                "spend": int(row["推广花费_分"]),
                "attributed": int(row["推广归因成交金额_分"]),
                "roi": float(row["推广ROI"]),
                "profit": int(row["含推广利润_分"]),
                "missing": int(row["成本运费缺失行数"]),
                "actionPriority": str(row["运营动作优先级"]),
                "action": str(row["运营动作"]),
            }
        )
    return rows


def write_html(result: ValidationResult, config: RunConfig, path: Path) -> None:
    summary = result.analysis.summary
    status = result.reconciliation.status.value
    rows = _link_rows(result)
    critical_actions = sum(1 for row in rows if row["actionPriority"] == "高")
    profitable = sum(1 for row in rows if row["profitState"] == "盈利")
    losing = sum(1 for row in rows if row["profitState"] == "亏损")
    report_data = _json_for_script(rows)
    status_class = "final" if status == "FINAL" else "provisional"
    status_note = (
        "核算数据完整，可用于正式经营复盘。"
        if status == "FINAL"
        else "部分链接成本或运费缺失，利润为暂算；请先处理行动清单中的数据问题。"
    )
    html_text = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>店铺经营复盘｜{_safe(config.start_date)} 至 {_safe(config.end_date)}</title>
<style>
:root{{--bg:#f3f6f8;--paper:#fff;--ink:#142536;--ink2:#435567;--muted:#71808d;--line:#d7e0e5;--soft:#eaf0f3;--navy:#173e5c;--teal:#14796e;--teal-bg:#e6f4f1;--amber:#9a5c0a;--amber-bg:#fff1d9;--red:#ae3d45;--red-bg:#fae9eb;--blue:#2f6592;--shadow:0 12px 30px rgba(20,37,54,.08)}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#0f1922;--paper:#172633;--ink:#edf4f8;--ink2:#c1ced7;--muted:#91a2ae;--line:#344754;--soft:#203440;--navy:#93c9eb;--teal:#69d2c3;--teal-bg:#193d39;--amber:#ffc166;--amber-bg:#46341b;--red:#ff9299;--red-bg:#43262c;--blue:#93c5eb;--shadow:0 12px 30px rgba(0,0,0,.22)}}}}
:root[data-theme="dark"]{{--bg:#0f1922;--paper:#172633;--ink:#edf4f8;--ink2:#c1ced7;--muted:#91a2ae;--line:#344754;--soft:#203440;--navy:#93c9eb;--teal:#69d2c3;--teal-bg:#193d39;--amber:#ffc166;--amber-bg:#46341b;--red:#ff9299;--red-bg:#43262c;--blue:#93c5eb;--shadow:0 12px 30px rgba(0,0,0,.22)}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.65 "Microsoft YaHei UI","Microsoft YaHei",sans-serif;overflow-x:hidden}}.wrap{{max-width:1480px;margin:auto;padding:24px}}.top{{background:var(--paper);border:1px solid var(--line);box-shadow:var(--shadow);padding:26px 30px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:center}}h1,h2{{font-family:"STZhongsong","SimSun",serif;text-wrap:balance}}h1{{font-size:clamp(28px,4vw,46px);margin:6px 0 8px;line-height:1.12}}h2{{font-size:25px;margin:0}}.eyebrow{{font:700 11px Consolas,monospace;letter-spacing:.12em;color:var(--blue)}}.meta{{color:var(--muted)}}.status{{padding:14px 18px;border:1px solid currentColor;font-weight:700;max-width:330px}}.status.final{{color:var(--teal);background:var(--teal-bg)}}.status.provisional{{color:var(--amber);background:var(--amber-bg)}}.status b{{display:block;font:700 20px Consolas,monospace}}.section{{margin-top:20px;background:var(--paper);border:1px solid var(--line);box-shadow:var(--shadow);padding:26px}}.section-head{{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:20px}}.section-head p{{margin:0;color:var(--muted)}}.ledger{{display:grid;grid-template-columns:repeat(9,minmax(120px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);overflow:auto}}.ledger-item{{background:var(--paper);padding:16px;min-width:120px}}.ledger-item .op{{font:700 18px Consolas;color:var(--muted)}}.ledger-item b{{display:block;font:700 18px Consolas,monospace;margin-top:8px;white-space:nowrap}}.ledger-item span{{color:var(--muted);font-size:12px}}.ledger-item.result{{background:var(--teal-bg);color:var(--teal)}}.ledger-item.loss b{{color:var(--red)}}.coverage{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}.tile{{padding:16px;border:1px solid var(--line);background:var(--paper)}}.tile b{{display:block;font:700 25px Consolas,monospace}}.tile span{{color:var(--muted);font-size:12px}}.tile.alert{{background:var(--amber-bg);color:var(--amber)}}.controls{{display:grid;grid-template-columns:minmax(230px,1fr) repeat(3,minmax(140px,200px));gap:10px;margin-bottom:14px}}input,select{{width:100%;padding:10px 12px;border:1px solid var(--line);background:var(--paper);color:var(--ink);font:inherit}}input:focus,select:focus,a:focus{{outline:2px solid var(--blue);outline-offset:2px}}.table-wrap{{overflow:auto;max-height:70vh;border:1px solid var(--line)}}table{{border-collapse:collapse;width:100%;min-width:1700px;font-size:12px}}th,td{{padding:10px 11px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}th{{position:sticky;top:0;background:var(--navy);color:var(--paper);z-index:2;text-align:right}}th:nth-child(-n+4),td:nth-child(-n+4),th:last-child,td:last-child{{text-align:left}}td.title{{max-width:280px;overflow:hidden;text-overflow:ellipsis}}td.money{{font-family:Consolas,monospace}}a{{color:var(--blue)}}.chip{{display:inline-block;padding:2px 7px;border:1px solid currentColor;font-weight:700}}.chip.good{{color:var(--teal)}}.chip.warn{{color:var(--amber)}}.chip.bad{{color:var(--red)}}.action{{max-width:260px;white-space:normal}}.empty{{padding:32px;text-align:center;color:var(--muted)}}.note{{margin-top:16px;padding:14px 16px;background:var(--soft);color:var(--ink2)}}.footer{{padding:24px;text-align:center;color:var(--muted);font-size:12px}}@media(max-width:900px){{.top{{grid-template-columns:1fr}}.coverage{{grid-template-columns:repeat(2,1fr)}}.controls{{grid-template-columns:1fr 1fr}}}}@media(max-width:560px){{.wrap{{padding:10px}}.top,.section{{padding:18px}}.coverage,.controls{{grid-template-columns:1fr}}}}@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
</style></head><body><div class="wrap">
<header class="top"><div><div class="eyebrow">STORE PROFIT REVIEW · {_safe(config.platform.value.upper())}</div><h1>店铺经营复盘</h1><div class="meta">{_safe(config.start_date)} 至 {_safe(config.end_date)} · 程序 v{_safe(__version__)} · 逐行分币核算</div></div><div class="status {status_class}"><b>{status}</b>{_safe(status_note)}</div></header>
<section class="section"><div class="section-head"><div><h2>经营结果是怎样扣出来的</h2><p>从已核算销售额出发，逐项扣除退款、商品与经营费用。</p></div><b>{_percent(summary['含推广净利率'])}</b></div><div class="ledger">
<div class="ledger-item"><div class="op">起点</div><span>已核算销售额</span><b>{_money(summary['已核算销售额_分'])}</b></div>
<div class="ledger-item loss"><div class="op">−</div><span>有效退款</span><b>{_money(summary['已核算有效退款_分'])}</b></div>
<div class="ledger-item loss"><div class="op">−</div><span>货品成本</span><b>{_money(summary['已核算货品成本_分'])}</b></div>
<div class="ledger-item loss"><div class="op">−</div><span>运费</span><b>{_money(summary['已核算运费_分'])}</b></div>
<div class="ledger-item loss"><div class="op">−</div><span>平台扣点</span><b>{_money(summary['已核算平台扣点_分'])}</b></div>
<div class="ledger-item loss"><div class="op">−</div><span>综合税赋</span><b>{_money(summary['已核算综合税赋_分'])}</b></div>
<div class="ledger-item loss"><div class="op">−</div><span>关闭发货损失</span><b>{_money(summary['关闭已发货损失_分'])}</b></div>
<div class="ledger-item loss"><div class="op">−</div><span>推广花费</span><b>{_money(summary['推广花费_分'])}</b></div>
<div class="ledger-item result"><div class="op">=</div><span>含推广净利润</span><b>{_money(summary['含推广净利润_分'])}</b></div></div>
<div class="note">推广归因成交金额 {_money(summary['推广归因成交金额_分'])} 仅用于投产分析，不重复计入订单销售额。</div></section>
<section class="section"><div class="section-head"><div><h2>链接覆盖与风险入口</h2><p>先看结构，再进入具体链接处理。</p></div></div><div class="coverage"><div class="tile"><b>{summary['有效商品链接']}</b><span>有效链接</span></div><div class="tile"><b>{summary['订单+推广链接']}</b><span>订单+推广</span></div><div class="tile"><b>{summary['仅订单链接']}</b><span>仅订单</span></div><div class="tile"><b>{summary['仅推广链接']}</b><span>仅推广</span></div><div class="tile"><b>{profitable}</b><span>盈利链接</span></div><div class="tile alert"><b>{critical_actions}</b><span>优先处理</span></div></div></section>
<section class="section"><div class="section-head"><div><h2>链接诊断与行动清单</h2><p><span id="visibleCount">{len(rows)}</span> 条结果 · 亏损链接 {losing} 条</p></div></div><div class="controls"><input id="search" type="search" placeholder="搜索商品ID或标题"><select id="coverage"><option value="">全部覆盖</option><option>订单+推广</option><option>仅订单</option><option>仅推广</option></select><select id="accounting"><option value="">全部核算状态</option><option>完整</option><option>暂算</option></select><select id="sort"><option value="profitAsc">含推广利润：低到高</option><option value="profitDesc">含推广利润：高到低</option><option value="spendDesc">推广花费：高到低</option><option value="roiDesc">ROI：高到低</option><option value="salesDesc">销售额：高到低</option><option value="refundDesc">退款：高到低</option></select></div><div class="table-wrap"><table><thead><tr><th>商品ID</th><th>商品标题</th><th>覆盖</th><th>状态</th><th>销售额</th><th>退款</th><th>成本</th><th>运费</th><th>平台费</th><th>税赋</th><th>关闭损失</th><th>推广花费</th><th>归因成交</th><th>ROI</th><th>含推广利润</th><th>运营动作</th></tr></thead><tbody id="rows"></tbody></table><div class="empty" id="empty" hidden>没有符合当前筛选条件的链接。调整筛选后重试。</div></div><div class="note">动作标签由确定性规则生成，只用于复盘提示，不会自动修改推广计划。PROVISIONAL 报告中的链接利润不得当作最终利润。</div></section>
<div class="footer">订单利润核算标准化程序 · 店铺经营复盘 · 自包含离线报告</div></div>
<script>const DATA={report_data};const money=v=>'¥'+(v/100).toLocaleString('zh-CN',{{minimumFractionDigits:2,maximumFractionDigits:2}});const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const profitCls=v=>v==='亏损'?'bad':'good';const accountingCls=v=>v==='暂算'?'warn':'good';function render(){{const q=document.querySelector('#search').value.trim().toLowerCase(),cov=document.querySelector('#coverage').value,acc=document.querySelector('#accounting').value,sort=document.querySelector('#sort').value;let rows=DATA.filter(r=>(!q||(r.id+' '+r.title).toLowerCase().includes(q))&&(!cov||r.coverage===cov)&&(!acc||r.accounting===acc));const key={{profitAsc:['profit',1],profitDesc:['profit',-1],spendDesc:['spend',-1],roiDesc:['roi',-1],salesDesc:['sales',-1],refundDesc:['refund',-1]}}[sort];rows.sort((a,b)=>(a[key[0]]-b[key[0]])*key[1]);document.querySelector('#rows').innerHTML=rows.map(r=>`<tr><td><a href="${{esc(r.url)}}" target="_blank" rel="noopener noreferrer">${{esc(r.id)}}</a></td><td class="title" title="${{esc(r.title)}}">${{esc(r.title)}}</td><td>${{esc(r.coverage)}}</td><td><span class="chip ${{accountingCls(r.accounting)}}">${{esc(r.accounting)}}</span></td><td class="money">${{money(r.sales)}}</td><td class="money">${{money(r.refund)}}</td><td class="money">${{money(r.cost)}}</td><td class="money">${{money(r.freight)}}</td><td class="money">${{money(r.platformFee)}}</td><td class="money">${{money(r.tax)}}</td><td class="money">${{money(r.closedLoss)}}</td><td class="money">${{money(r.spend)}}</td><td class="money">${{money(r.attributed)}}</td><td class="money">${{r.roi.toFixed(2)}}</td><td class="money"><span class="chip ${{profitCls(r.profitState)}}">${{money(r.profit)}}</span></td><td class="action">${{esc(r.action)}}</td></tr>`).join('');document.querySelector('#visibleCount').textContent=rows.length;document.querySelector('#empty').hidden=rows.length!==0}}document.querySelectorAll('input,select').forEach(e=>e.addEventListener('input',render));render();</script></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
