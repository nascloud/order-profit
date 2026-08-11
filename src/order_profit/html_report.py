"""生成自包含的四视图离线经营报表。"""

from __future__ import annotations

import html
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from order_profit.config import RunConfig


def _json_value(value: Any) -> Any:
    if value is None or (not isinstance(value, (str, list, dict)) and pd.isna(value)):
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(key): _json_value(value) for key, value in row.items()} for row in frame.to_dict("records")]


def _json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def write_html(result: Any, config: RunConfig, path: Path) -> None:
    analysis = result.analysis
    summary = analysis.summary
    links = analysis.links
    daily = analysis.daily
    products = analysis.products
    payload = {
        "summary": {key: _json_value(value) for key, value in summary.items()},
        "daily": _records(daily), "products": _records(products), "links": _records(links),
    }
    data = _json_for_script(payload)
    status = html.escape(result.reconciliation.status.value)
    title = "已核算部分经营贡献利润" if status == "PROVISIONAL" else "含推广经营贡献利润"
    page = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>店铺经营复盘</title><style>
:root{{--ink:#17202a;--muted:#65727e;--line:#d9e0e5;--paper:#f5f7f8;--panel:#fff;--brand:#176b54;--warn:#a65d00;--bad:#b42318}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 Arial,"Microsoft YaHei",sans-serif;letter-spacing:0}}
header{{background:#fff;border-bottom:1px solid var(--line);padding:18px 28px;display:flex;justify-content:space-between;align-items:end;gap:16px}}h1{{font-size:24px;margin:0}}.meta{{color:var(--muted);text-align:right}}
nav{{display:flex;gap:4px;padding:10px 28px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:3}}button,select,input{{font:inherit}}nav button{{border:0;background:transparent;padding:9px 14px;cursor:pointer}}nav button.active{{color:var(--brand);border-bottom:2px solid var(--brand);font-weight:700}}
main{{padding:22px 28px 40px;max-width:1600px;margin:auto}}.view[hidden]{{display:none}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin-top:22px}}.metric{{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px;min-height:96px}}.metric span{{color:var(--muted)}}.metric b{{display:block;font-size:24px;margin:7px 0 2px}}.metric small{{color:var(--muted)}}.negative{{color:var(--bad)!important}}
.calc-section{{padding:18px 0 20px;border-top:1px solid var(--line)}}.calc-section:first-child{{padding-top:0;border-top:0}}.calc-head{{display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-bottom:12px}}.calc-head h2{{font-size:17px;margin:0}}.calc-head span{{color:var(--muted);font-size:13px}}.equation-scroll{{overflow-x:auto;padding-bottom:5px}}.equation{{display:flex;align-items:stretch;width:max-content;min-width:100%}}.term{{width:170px;min-height:90px;padding:11px 10px 10px;border-top:3px solid #91a19b;background:#fff}}.term.refund{{border-color:var(--bad)}}.term.cost{{border-color:var(--warn)}}.term.result{{width:220px;border-color:var(--brand);background:#eef6f3}}.term span{{display:block;color:var(--muted);white-space:normal}}.term b{{display:block;font-size:21px;margin-top:10px;white-space:nowrap}}.term small{{display:block;color:var(--muted);margin-top:3px}}.operator{{width:42px;min-width:42px;display:grid;place-items:center;color:#53615c;font-size:25px;font-weight:700}}.equation+.equation{{margin-top:14px}}.equation:not(.profit-equation) .term{{width:220px}}.equation:not(.profit-equation) .term span{{white-space:nowrap}}.profit-equation .term{{width:132px}}.profit-equation .term.result{{width:190px}}.profit-equation .term b{{font-size:18px}}.profit-equation .operator{{width:28px;min-width:28px}}
.controls{{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}}.controls input,.controls select{{height:36px;border:1px solid var(--line);background:#fff;padding:0 10px;border-radius:4px}}.controls input{{min-width:220px}}
.table-wrap{{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:6px;max-height:68vh}}table{{border-collapse:collapse;width:100%;min-width:1100px}}th,td{{padding:9px 10px;border-bottom:1px solid #edf0f2;text-align:right;white-space:nowrap}}th{{position:sticky;top:0;background:#eef3f1;color:#32463f;z-index:1}}th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){{text-align:left}}td small{{display:block;color:var(--muted)}}.tag{{font-weight:700;color:var(--brand)}}footer{{padding:18px 28px;color:var(--muted);border-top:1px solid var(--line);background:#fff}}
@media(max-width:700px){{header{{padding:14px 16px;align-items:start;flex-direction:column}}.meta{{text-align:left}}nav,main{{padding-left:12px;padding-right:12px}}nav{{overflow:auto}}.metrics{{grid-template-columns:1fr 1fr}}.metric b{{font-size:20px}}.calc-head{{align-items:start;flex-direction:column;gap:2px}}.equation{{width:100%;min-width:0;flex-direction:column}}.term,.term.result,.equation:not(.profit-equation) .term,.profit-equation .term,.profit-equation .term.result{{width:100%}}.equation:not(.profit-equation) .term span{{white-space:normal}}.operator,.profit-equation .operator{{width:100%;height:30px;min-height:30px}}}}
</style></head><body>
<header><div><h1>店铺经营复盘</h1><div>{config.start_date.isoformat()} 至 {config.end_date.isoformat()}</div></div><div class="meta"><b>{status}</b><br>{html.escape(config.platform.value)} · 平台费 {config.platform_fee_rate:.2%} · 税赋 {config.tax_rate:.2%}</div></header>
<nav><button class="active" data-view="overview">经营总览</button><button data-view="daily">每日经营</button><button data-view="products">产品分析</button><button data-view="links">链接分析</button></nav>
<main>
<section id="overview" class="view"><div class="calc-section"><div class="calc-head"><h2>全部订单销售链</h2><span>按订单付款日期归属</span></div><div class="equation-scroll"><div class="equation" id="salesEquation"></div></div></div><div class="calc-section"><div class="calc-head"><h2>已核算利润链</h2><span id="accountingCoverage"></span></div><div class="equation-scroll"><div class="equation" id="accountedEquation"></div><div class="equation profit-equation" id="profitEquation"></div></div></div><div class="metrics" id="summaryMetrics"></div></section>
<section id="daily" class="view" hidden><div class="table-wrap"><table id="dailyTable"></table></div></section>
<section id="products" class="view" hidden><div class="table-wrap"><table id="productTable"></table></div></section>
<section id="links" class="view" hidden><div class="controls"><input id="search" type="search" placeholder="搜索商品ID或标题"><select id="productFilter"><option value="">全部产品</option></select><select id="sabc"><option value="">全部 SABC</option></select><select id="profit"><option value="">全部盈亏</option><option>盈利</option><option>亏损</option><option>持平</option><option>待核算</option></select><select id="coverage"><option value="">全部覆盖</option><option>订单+推广</option><option>仅订单</option><option>仅推广</option></select><select id="accounting"><option value="">全部核算状态</option><option>已核算</option><option>成本或运费缺失</option></select><select id="sort"><option value="profitDesc">经营贡献利润：高到低</option><option value="salesDesc">销售额：高到低</option><option value="marginDesc">经营贡献利润率：高到低</option><option value="spendDesc">推广花费：高到低</option><option value="roiDesc">推广投产比：高到低</option><option value="refundDesc">退款率：高到低</option></select></div><div class="table-wrap"><table><thead id="linkHead"></thead><tbody id="rows"></tbody></table></div></section>
</main><footer>平台扣点与综合税赋为管理估算值。产品推广数据为链接级分摊估算。SABC 阈值：{config.s_profit_share:.0%}/{config.a_profit_share:.0%}；配置：{html.escape(str(config.sabc_config or '默认'))}。</footer>
<script>const DATA={data};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));const money=v=>v==null?'--':'¥'+(v/100).toLocaleString('zh-CN',{{minimumFractionDigits:2,maximumFractionDigits:2}});const pct=v=>v==null?'暂无比例':(v*100).toFixed(2)+'%';const num=v=>v==null?'--':Number(v).toLocaleString('zh-CN');const roi=v=>v==null?'--':Number(v).toFixed(2)+'x';
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x===b));document.querySelectorAll('.view').forEach(x=>x.hidden=x.id!==b.dataset.view)}});
const S=DATA.summary,accounted=S['已核算销售额_分']||0,accountedRefund=S['已核算订单批次成功退款_分']||0,accountedNet=accounted-accountedRefund;const term=(label,value,tone='',note='')=>`<div class="term ${{tone}}"><span>${{label}}</span><b class="${{value<0?'negative':''}}">${{money(value)}}</b>${{note?`<small>${{note}}</small>`:''}}</div>`,op=value=>`<div class="operator" aria-hidden="true">${{value}}</div>`;
const paid=S['已付款销售额_分']||0,allRefund=S['订单批次成功退款金额_分']||0,share=(value,base)=>pct(base?value/base:null);document.querySelector('#salesEquation').innerHTML=term('净销售额',S['净销售额_分'],'result',`占已付款销售额 ${{share(S['净销售额_分'],paid)}}`)+op('=')+term('已付款销售额',paid,'',`销售基准 ${{pct(paid?1:null)}}`)+op('−')+term('全部订单批次成功退款',allRefund,'refund',`退款率 ${{share(allRefund,paid)}}`);
document.querySelector('#accountedEquation').innerHTML=term('已核算净销售额',accountedNet,'result',`占已核算销售额 ${{share(accountedNet,accounted)}}`)+op('=')+term('已核算销售额',accounted,'',`占已付款销售额 ${{share(accounted,paid)}}`)+op('−')+term('已核算订单批次成功退款',accountedRefund,'refund',`占已核算销售额 ${{share(accountedRefund,accounted)}}`);
document.querySelector('#profitEquation').innerHTML=term('{title}',S['含推广经营贡献利润_分'],'result',`利润率 ${{pct(S['经营贡献利润率'])}}`)+op('=')+term('已核算净销售额',accountedNet,'',`净销售额基准 ${{pct(accountedNet?1:null)}}`)+op('−')+term('货品成本',S['已核算货品成本_分'],'cost',`占净销售额 ${{share(S['已核算货品成本_分'],accountedNet)}}`)+op('−')+term('运费',S['已核算运费_分'],'cost',`占净销售额 ${{share(S['已核算运费_分'],accountedNet)}}`)+op('−')+term('平台扣点（估算）',S['已核算平台扣点_分'],'cost',`占净销售额 ${{share(S['已核算平台扣点_分'],accountedNet)}}`)+op('−')+term('综合税赋（估算）',S['已核算综合税赋_分'],'cost',`占净销售额 ${{share(S['已核算综合税赋_分'],accountedNet)}}`)+op('−')+term('关闭已发货损失',S['关闭已发货损失_分'],'cost',`占净销售额 ${{share(S['关闭已发货损失_分'],accountedNet)}}`)+op('−')+term('推广花费',S['推广花费_分'],'cost',`占净销售额 ${{share(S['推广花费_分'],accountedNet)}}`);
document.querySelector('#accountingCoverage').textContent=`销售额核算覆盖率 ${{pct(S['销售额核算覆盖率'])}}`;
const cards=[['期间退款完结金额',S['期间退款完结金额_分'],'退款完结日期口径','money'],['推广花费',S['推广花费_分'],`占已核算净销售额 ${{pct(accountedNet?S['推广花费_分']/accountedNet:null)}}`,'money'],['推广归因成交金额',S['推广归因成交金额_分'],`推广投产比 ${{roi(S['推广投产比'])}}`,'money'],['退款订单率',S['退款订单率'],'主订单口径','ratio'],['付款后关闭率',S['付款后关闭率'],'主订单口径','ratio'],['关闭已发货率',S['关闭已发货率'],'主订单口径','ratio']];document.querySelector('#summaryMetrics').innerHTML=cards.map(c=>`<div class="metric"><span>${{c[0]}}</span><b class="${{c[1]<0?'negative':''}}">${{c[3]==='ratio'?pct(c[1]):money(c[1])}}</b><small>${{c[2]}}</small></div>`).join('');
function table(el,rows,cols){{const node=document.querySelector(el);node.innerHTML='<thead><tr>'+cols.map(c=>`<th>${{c[0]}}</th>`).join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(c=>`<td>${{c[2]?c[2](r[c[1]],r):esc(r[c[1]]??'--')}}</td>`).join('')+'</tr>').join('')+'</tbody>'}}
const M=v=>money(v),P=v=>pct(v),N=v=>num(v),R=v=>roi(v);table('#dailyTable',DATA.daily,[['日期','日期'],['主订单数','已付款主订单数',N],['购买数量','购买数量',N],['销售额','销售额_分',M],['占期间销售','占期间销售比例',P],['订单批次退款','订单批次成功退款_分',M],['期间退款完结','期间退款完结金额_分',M],['成本','货品成本_分',M],['成本率','成本率',P],['运费','运费_分',M],['运费率','运费率',P],['平台费率','平台费率',P],['税费率','税费率',P],['推广花费','推广花费_分',M],['推广费率','推广费率',P],['推广投产比','推广投产比',R],['经营贡献利润','含推广经营贡献利润_分',M],['利润率','经营贡献利润率',P],['核算覆盖率','核算覆盖率',P]]);
const PM=(v,r)=>r['经营贡献利润率状态']==='已核算'?P(v):esc(r['经营贡献利润率状态']);table('#productTable',DATA.products,[['产品名称','产品名称'],['SKU数','SKU数',N],['链接数','商品链接数',N],['主订单数','已付款主订单数',N],['销售额','销售额_分',M],['净销售额','净销售额_分',M],['销售贡献率','销售贡献率',P],['订单批次退款','订单批次成功退款_分',M],['推广花费','推广花费_分',M],['推广投产比','推广投产比',R],['经营贡献利润','含推广经营贡献利润_分',M],['利润率','经营贡献利润率',PM],['S','S链接数',N],['A','A链接数',N],['B','B链接数',N],['C','C链接数',N],['待核算','待核算链接数',N]]);
const cols=[['SABC','SABC等级'],['产品','产品名称'],['商品ID','商品ID'],['商品标题','商品标题'],['覆盖','数据覆盖'],['核算','核算状态'],['销售额','销售额_分',M],['销售贡献率','销售贡献率',P],['退款','订单批次成功退款_分',M],['退款率','退款率',P],['成本','货品成本_分',M],['运费','运费_分',M],['推广花费','推广花费_分',M],['推广投产比','推广投产比',R],['经营贡献利润','含推广经营贡献利润_分',M],['利润率','经营贡献利润率',P],['盈利贡献/亏损占比','盈利贡献率',P],['运营动作','运营动作']];document.querySelector('#linkHead').innerHTML='<tr>'+cols.map(c=>`<th>${{c[0]}}</th>`).join('')+'</tr>';
const controls=['search','productFilter','sabc','profit','coverage','accounting','sort'].map(id=>document.querySelector('#'+id));for(const [id,key] of [['productFilter','产品名称'],['sabc','SABC等级']]){{const el=document.querySelector('#'+id);[...new Set(DATA.links.map(x=>x[key]).filter(Boolean))].sort().forEach(v=>el.add(new Option(v,v)))}}
function render(){{let a=DATA.links.filter(r=>(!controls[0].value||(`${{r['商品ID']}} ${{r['商品标题']}}`).toLowerCase().includes(controls[0].value.toLowerCase()))&&(!controls[1].value||r['产品名称']===controls[1].value)&&(!controls[2].value||r['SABC等级']===controls[2].value)&&(!controls[3].value||r['盈利状态']===controls[3].value)&&(!controls[4].value||r['数据覆盖']===controls[4].value)&&(!controls[5].value||r['核算状态']===controls[5].value));const sorts={{profitDesc:['含推广经营贡献利润_分',-1],salesDesc:['销售额_分',-1],marginDesc:['经营贡献利润率',-1],spendDesc:['推广花费_分',-1],roiDesc:['推广投产比',-1],refundDesc:['退款率',-1]}};const [k,d]=sorts[controls[6].value];a.sort((x,y)=>((x[k]??-Infinity)-(y[k]??-Infinity))*d);document.querySelector('#rows').innerHTML=a.map(r=>'<tr>'+cols.map(c=>{{let v=c[2]?c[2](r[c[1]],r):esc(r[c[1]]??'--');if(c[1]==='盈利贡献率'&&r['亏损占比']!=null)v=P(r['亏损占比']);return `<td class="${{r['含推广经营贡献利润_分']<0&&c[1]==='含推广经营贡献利润_分'?'negative':''}}">${{v}}</td>`}}).join('')+'</tr>').join('')}}controls.forEach(x=>x.oninput=render);render();
</script></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8", newline="\n")
