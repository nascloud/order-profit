"""推广、每日、产品、链接和店铺统一经营聚合。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

import pandas as pd

from order_profit.config import RunConfig
from order_profit.errors import NormalizationError
from order_profit.inputs import LoadedTable
from order_profit.models import Issue, Severity, SourceLocation
from order_profit.profit import ProfitResult
from order_profit.rules import has_brush_marker


@dataclass(frozen=True, slots=True)
class PromotionResult:
    detail: pd.DataFrame
    out_of_period: pd.DataFrame
    daily: pd.DataFrame
    products: pd.DataFrame
    issues: tuple[Issue, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    profit: ProfitResult
    promotion: PromotionResult
    links: pd.DataFrame
    sku: pd.DataFrame
    summary: dict[str, object]
    daily: pd.DataFrame = field(default_factory=pd.DataFrame)
    products: pd.DataFrame = field(default_factory=pd.DataFrame)
    issues: tuple[Issue, ...] = ()


def _ratio(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) if denominator else Decimal("0")


def _optional_ratio(numerator: int, denominator: int) -> Decimal | None:
    return Decimal(numerator) / Decimal(denominator) if denominator else None


def _sum(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].sum()) if not frame.empty and column in frame else 0


def _brush_amount(frame: pd.DataFrame) -> int:
    if frame.empty or "商家备注" not in frame:
        return 0
    mask = frame["商家备注"].map(has_brush_marker)
    return _sum(frame[mask], "实收金额_分")


def _non_brush(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "商家备注" not in frame:
        return frame
    return frame[~frame["商家备注"].map(has_brush_marker)]


def _real_sales(sales: int, refunds: int, brush: int) -> int:
    return sales - refunds - brush


def _promotion_metrics(frame: pd.DataFrame) -> dict[str, object]:
    impressions = _sum(frame, "展现量_标准")
    clicks = _sum(frame, "点击量_标准")
    spend = _sum(frame, "花费_分")
    attributed = _sum(frame, "总成交金额_分")
    transactions = _sum(frame, "总成交笔数_标准")
    missing = [name for name, denominator in (("推广投产比", spend), ("平均点击花费", clicks), ("点击率", impressions)) if not denominator]
    return {
        "推广展现量": impressions,
        "推广点击量": clicks,
        "推广花费_分": spend,
        "推广归因成交金额_分": attributed,
        "推广成交笔数": transactions,
        "推广投产比": _ratio(attributed, spend),
        "平均点击花费_分": _ratio(spend, clicks),
        "点击率": _ratio(clicks, impressions),
        "零分母状态": "、".join(missing),
    }


def _aggregate_promotion_frame(detail: pd.DataFrame, key: str) -> pd.DataFrame:
    return pd.DataFrame([{key: value, **_promotion_metrics(group)} for value, group in detail.groupby(key, sort=True, dropna=False)])


def aggregate_promotion(promotion: LoadedTable | None, config: RunConfig) -> PromotionResult:
    if promotion is None:
        empty = pd.DataFrame()
        return PromotionResult(empty, empty, empty, empty)
    data = promotion.data.copy()
    start, end = config.period_bounds()
    mask = data["日期_标准"].map(lambda value: start <= value < end)
    detail, out = data.loc[mask].copy(), data.loc[~mask].copy()
    empty_id = detail["主体ID"].eq("")
    if empty_id.any():
        row = detail.loc[empty_id].iloc[0]
        issue = Issue("PROMOTION_SUBJECT_ID_REQUIRED", Severity.ERROR, "期间内推广数据主体ID不能为空", SourceLocation(file=str(promotion.metadata.path), row=int(row["source_row_number"]), field="主体ID"), suggestion="请重新导出包含主体ID的推广报表")
        raise NormalizationError(issue.message, code=issue.code, issues=[issue])
    if not detail.empty:
        detail["推广日期"] = detail["日期_标准"].map(lambda value: value.date().isoformat())
    daily = _aggregate_promotion_frame(detail, "推广日期") if not detail.empty else pd.DataFrame()
    products = _aggregate_promotion_frame(detail, "主体ID") if not detail.empty else pd.DataFrame()
    if not products.empty:
        names = detail.sort_values(["日期_标准", "source_row_number"]).drop_duplicates("主体ID", keep="last").set_index("主体ID")["主体名称"]
        products["主体名称"] = products["主体ID"].map(names)
    return PromotionResult(detail, out, daily, products, promotion.issues)


def _paid_frames(profit: ProfitResult) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for name, source in (("正常订单", profit.normal), ("付款后关闭已发货", profit.closed_shipped), ("付款后关闭无物流", profit.closed_unshipped)):
        if not source.empty:
            frame = source.copy()
            frame["订单类型"] = name
            frames.append(frame)
    return frames


def _paid(profit: ProfitResult) -> pd.DataFrame:
    frames = _paid_frames(profit)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _row_profit(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    normal = frame[frame["订单类型"] == "正常订单"]
    closed = frame[frame["订单类型"] != "正常订单"]
    closed_profit = _sum(closed, "关闭明细利润_分") if "关闭明细利润_分" in closed else -_sum(closed, "关闭已发货损失_分")
    return _sum(normal, "正常订单利润_分") + closed_profit


def _latest_titles(paid: pd.DataFrame) -> dict[str, str]:
    if paid.empty:
        return {}
    latest = paid.sort_values(["订单付款时间_标准", "source_row_number"]).drop_duplicates("商品ID", keep="last")
    return dict(zip(latest["商品ID"].map(str), latest["商品标题"].map(str), strict=True))


def _link_product_name(frame: pd.DataFrame) -> str:
    names = sorted({str(value).strip() or "未归类" for value in frame.get("产品名称", pd.Series(dtype=object)).fillna("")})
    return names[0] if len(names) == 1 else ("多产品" if len(names) > 1 else "未归类")


def _link_product_members(frame: pd.DataFrame) -> str:
    if frame.empty or "产品名称" not in frame:
        return "未归类"
    names = sorted({str(value).strip() or "未归类" for value in frame["产品名称"].fillna("")})
    return "、".join(names)


def build_link_report(profit: ProfitResult, promotion: PromotionResult, config: RunConfig, *, provisional: bool = False) -> pd.DataFrame:
    paid = _paid(profit)
    order_ids = set(paid["商品ID"].map(str)) if not paid.empty else set()
    promo_ids = set(promotion.detail["主体ID"].map(str)) if not promotion.detail.empty else set()
    promo = promotion.products.set_index("主体ID").to_dict("index") if not promotion.products.empty else {}
    titles = _latest_titles(paid)
    rows: list[dict[str, object]] = []
    for link_id in sorted(order_ids | promo_ids):
        orders = paid[paid["商品ID"].map(str) == link_id].copy() if not paid.empty else pd.DataFrame()
        complete = orders[orders["核算状态"] == "已核算"] if not orders.empty else orders
        normal_complete = complete[complete["订单类型"] == "正常订单"] if not complete.empty else complete
        normal_costed = _non_brush(normal_complete)
        closed_complete = complete[complete["订单类型"] == "付款后关闭已发货"] if not complete.empty else complete
        p = promo.get(link_id, {})
        sales, refunds = _sum(orders, "实收金额_分"), _sum(orders, "有效退款_分")
        brush = _brush_amount(orders)
        accounted_sales = _sum(complete, "实收金额_分")
        accounted_refunds = _sum(complete, "有效退款_分")
        accounted_net = accounted_sales - accounted_refunds
        spend, attributed = int(p.get("推广花费_分", 0)), int(p.get("推广归因成交金额_分", 0))
        operating_profit = _row_profit(complete)
        contribution = operating_profit - spend
        incomplete = int((orders["核算状态"] != "已核算").sum()) if not orders.empty else 0
        coverage = "订单+推广" if link_id in order_ids and link_id in promo_ids else ("仅订单" if link_id in order_ids else "仅推广")
        refund_rate = _optional_ratio(refunds, sales)
        tags: list[str] = []
        if incomplete: tags.append("补成本或运费")
        if coverage == "仅推广": tags.append("仅推广无订单")
        if coverage == "仅订单": tags.append("仅订单无推广")
        if refund_rate is not None and refund_rate >= Decimal("0.1"): tags.append("高退款")
        if _sum(closed_complete, "关闭已发货损失_分"): tags.append("关闭已发货损失")
        if spend and contribution < 0: tags.append("推广后亏损")
        elif spend and contribution > 0 and Decimal(str(p.get("推广投产比", 0))) >= Decimal("2"): tags.append("可加投观察")
        rows.append({
            "SABC等级": "待核算" if incomplete else "",
            "产品名称": _link_product_name(orders),
            "产品归属明细": _link_product_members(orders),
            "商品ID": link_id,
            "商品标题": titles.get(link_id) or str(p.get("主体名称", "")),
            "商品链接": f"https://item.taobao.com/item.htm?id={link_id}",
            "数据覆盖": coverage,
            "核算状态": "成本或运费缺失" if incomplete else "已核算",
            "主订单数": int(orders["主订单编号"].nunique()) if not orders.empty else 0,
            "购买数量": _sum(orders, "购买数量_标准"),
            "销售额_分": sales,
            "刷单金额_分": brush,
            "真实销售额_分": _real_sales(sales, refunds, brush),
            "已核算销售额_分": accounted_sales,
            "订单批次成功退款_分": refunds,
            "已核算订单批次成功退款_分": accounted_refunds,
            "货品成本_分": _sum(normal_costed, "核算成本_分"),
            "运费_分": _sum(normal_costed, "核算运费_分"),
            "刷单成本_分": _sum(normal_complete, "刷单成本_分"),
            "平台扣点_分": _sum(complete, "平台扣点_分"),
            "综合税赋_分": _sum(complete, "综合税赋_分"),
            "关闭已发货损失_分": _sum(closed_complete, "关闭已发货损失_分"),
            "推广展现量": int(p.get("推广展现量", 0)), "推广点击量": int(p.get("推广点击量", 0)),
            "点击率": p.get("点击率", Decimal("0")), "推广花费_分": spend,
            "推广归因成交金额_分": attributed, "推广成交笔数": int(p.get("推广成交笔数", 0)),
            "推广投产比": p.get("推广投产比", Decimal("0")),
            "推广前经营利润_分": operating_profit,
            "含推广经营贡献利润_分": contribution,
            "经营贡献利润率": _optional_ratio(contribution, accounted_net),
            "销售贡献率": None, "盈利贡献率": None, "亏损占比": None,
            "退款率": refund_rate, "推广费率": _optional_ratio(spend, accounted_net),
            "盈利状态": "待核算" if incomplete else ("盈利" if contribution > 0 else ("亏损" if contribution < 0 else "持平")),
            "成本运费缺失行数": incomplete,
            "运营动作优先级": "高" if incomplete or contribution < 0 else ("中" if tags else "低"),
            "运营动作": "、".join(tags) if tags else "保持观察",
        })
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    total_sales = _sum(result, "销售额_分")
    positive_total = _sum(result[result["含推广经营贡献利润_分"] > 0], "含推广经营贡献利润_分")
    loss_total = -_sum(result[result["含推广经营贡献利润_分"] < 0], "含推广经营贡献利润_分")
    result["销售贡献率"] = result["销售额_分"].map(lambda value: _optional_ratio(int(value), total_sales))
    ranked = result[(result["成本运费缺失行数"] == 0) & (result["含推广经营贡献利润_分"] > 0)].sort_values(["含推广经营贡献利润_分", "商品ID"], ascending=[False, True])
    cumulative = 0
    s_share = config.s_profit_share
    a_share = config.a_profit_share
    for index, row in ranked.iterrows():
        before = _ratio(cumulative, positive_total)
        grade = "S" if before < s_share else ("A" if before < a_share else "B")
        result.at[index, "SABC等级"] = f"暂算 {grade}" if provisional else grade
        result.at[index, "盈利贡献率"] = _optional_ratio(int(row["含推广经营贡献利润_分"]), positive_total)
        cumulative += int(row["含推广经营贡献利润_分"])
    losses = (result["成本运费缺失行数"] == 0) & (result["含推广经营贡献利润_分"] <= 0)
    result.loc[losses, "SABC等级"] = "暂算 C" if provisional else "C"
    result.loc[losses, "亏损占比"] = result.loc[losses, "含推广经营贡献利润_分"].map(lambda value: _optional_ratio(-int(value), loss_total))
    return result


def _allocate(total: int, weights: dict[str, int]) -> dict[str, int]:
    positive = {name: value for name, value in weights.items() if value > 0}
    if not positive:
        return {"未归类": total}
    denominator = sum(positive.values())
    result = {name: total * value // denominator for name, value in positive.items()}
    remainder = total - sum(result.values())
    for name in sorted(positive, key=lambda key: (-positive[key], key))[:remainder]:
        result[name] += 1
    return result


def _product_promotion(paid: pd.DataFrame, promotion: PromotionResult) -> dict[str, dict[str, int]]:
    allocated: dict[str, dict[str, int]] = {}
    promo = promotion.products.set_index("主体ID").to_dict("index") if not promotion.products.empty else {}
    for link_id, values in promo.items():
        orders = paid[paid["商品ID"].map(str) == str(link_id)] if not paid.empty else pd.DataFrame()
        weights = orders.groupby("产品名称")["实收金额_分"].sum().astype(int).to_dict() if not orders.empty else {}
        for source, target in (("推广花费_分", "推广花费_分"), ("推广归因成交金额_分", "推广归因成交金额_分"), ("推广成交笔数", "推广成交笔数")):
            for name, amount in _allocate(int(values.get(source, 0)), weights).items():
                allocated.setdefault(name or "未归类", {}).setdefault(target, 0)
                allocated[name or "未归类"][target] += amount
    return allocated


def build_product_report(profit: ProfitResult, promotion: PromotionResult, links: pd.DataFrame) -> pd.DataFrame:
    paid = _paid(profit)
    if not paid.empty:
        names = paid["产品名称"] if "产品名称" in paid else pd.Series("未归类", index=paid.index)
        paid["产品名称"] = names.fillna("").map(lambda value: str(value).strip() or "未归类")
    promo = _product_promotion(paid, promotion)
    names = sorted((set(paid["产品名称"]) if not paid.empty else set()) | set(promo))
    rows: list[dict[str, object]] = []
    for name in names:
        group = paid[paid["产品名称"] == name] if not paid.empty else pd.DataFrame()
        complete = group[group["核算状态"] == "已核算"] if not group.empty else group
        normal = complete[complete["订单类型"] == "正常订单"] if not complete.empty else complete
        normal_costed = _non_brush(normal)
        closed = complete[complete["订单类型"] == "付款后关闭已发货"] if not complete.empty else complete
        p = promo.get(name, {})
        spend = int(p.get("推广花费_分", 0))
        contribution = _row_profit(complete) - spend
        product_links = links[links["产品归属明细"].map(lambda value: name in str(value).split("、"))] if not links.empty else links
        accountable_links = product_links[product_links["成本运费缺失行数"] == 0] if not product_links.empty else product_links
        incomplete = int((group["核算状态"] != "已核算").sum()) if not group.empty else 0
        sales = _sum(group, "实收金额_分")
        refunds = _sum(group, "有效退款_分")
        brush = _brush_amount(group)
        accounted_sales = _sum(complete, "实收金额_分")
        accounted_refunds = _sum(complete, "有效退款_分")
        net_sales = sales - refunds
        rows.append({
            "产品名称": name, "SKU数": int(group["商家编码"].replace("", pd.NA).nunique()) if not group.empty else 0,
            "商品链接数": len(product_links), "已付款主订单数": int(group["主订单编号"].nunique()) if not group.empty else 0,
            "购买数量": _sum(group, "购买数量_标准"), "销售额_分": sales, "净销售额_分": net_sales,
            "刷单金额_分": brush, "真实销售额_分": _real_sales(sales, refunds, brush),
            "已核算销售额_分": accounted_sales, "已核算净销售额_分": accounted_sales - accounted_refunds,
            "订单批次成功退款_分": refunds, "货品成本_分": _sum(normal_costed, "核算成本_分"), "运费_分": _sum(normal_costed, "核算运费_分"),
            "刷单成本_分": _sum(normal, "刷单成本_分"), "平台扣点_分": _sum(complete, "平台扣点_分"), "综合税赋_分": _sum(complete, "综合税赋_分"), "关闭已发货损失_分": _sum(closed, "关闭已发货损失_分"),
            "推广花费_分": spend, "推广归因成交金额_分": int(p.get("推广归因成交金额_分", 0)), "推广成交笔数": int(p.get("推广成交笔数", 0)),
            "推广前经营利润_分": _row_profit(complete), "含推广经营贡献利润_分": contribution,
            "经营贡献利润率状态": "待核算" if incomplete else ("已核算" if net_sales > 0 else "净销售额非正"),
            "盈利链接数": int((accountable_links["含推广经营贡献利润_分"] > 0).sum()) if not accountable_links.empty else 0,
            "亏损链接数": int((accountable_links["含推广经营贡献利润_分"] <= 0).sum()) if not accountable_links.empty else 0,
            "成本运费缺失行数": incomplete,
        })
    result = pd.DataFrame(rows)
    if result.empty: return result
    total_sales = _sum(result, "销售额_分")
    positive = _sum(result[(result["经营贡献利润率状态"] == "已核算") & (result["含推广经营贡献利润_分"] > 0)], "含推广经营贡献利润_分")
    result["销售贡献率"] = result["销售额_分"].map(lambda value: _optional_ratio(int(value), total_sales))
    result["退款率"] = result.apply(lambda row: _optional_ratio(int(row["订单批次成功退款_分"]), int(row["销售额_分"])), axis=1)
    result["推广投产比"] = result.apply(lambda row: _optional_ratio(int(row["推广归因成交金额_分"]), int(row["推广花费_分"])), axis=1)
    result["经营贡献利润率"] = result.apply(
        lambda row: _optional_ratio(int(row["含推广经营贡献利润_分"]), int(row["净销售额_分"]))
        if row["经营贡献利润率状态"] == "已核算" else None,
        axis=1,
    )
    result["店铺盈利贡献率"] = result.apply(
        lambda row: _optional_ratio(max(int(row["含推广经营贡献利润_分"]), 0), positive)
        if row["经营贡献利润率状态"] == "已核算" else None,
        axis=1,
    )
    for grade in ("S", "A", "B", "C"):
        result[f"{grade}链接数"] = result["产品名称"].map(lambda name: int(links[links["产品归属明细"].map(lambda value: name in str(value).split("、")) & links["SABC等级"].map(str).str.endswith(grade)].shape[0]))
    result["待核算链接数"] = result["产品名称"].map(lambda name: int(links[links["产品归属明细"].map(lambda value: name in str(value).split("、")) & (links["SABC等级"] == "待核算")].shape[0]))
    return result


def build_daily_report(profit: ProfitResult, promotion: PromotionResult, config: RunConfig) -> pd.DataFrame:
    paid = _paid(profit)
    promo = promotion.daily.set_index("推广日期").to_dict("index") if not promotion.daily.empty else {}
    after = profit.period_completed_refunds.copy()
    rows: list[dict[str, object]] = []
    day = config.start_date
    cumulative_sales = cumulative_profit = 0
    total_sales = _sum(paid, "实收金额_分")
    while day <= config.end_date:
        key = day.isoformat()
        orders = paid[paid["订单付款时间_标准"].map(lambda value: value.date() == day)] if not paid.empty else pd.DataFrame()
        complete = orders[orders["核算状态"] == "已核算"] if not orders.empty else orders
        normal = complete[complete["订单类型"] == "正常订单"] if not complete.empty else complete
        normal_costed = _non_brush(normal)
        closed = complete[complete["订单类型"] == "付款后关闭已发货"] if not complete.empty else complete
        p = promo.get(key, {})
        period_refund = _sum(after[after["退款完结时间_标准"].map(lambda value: value.date() == day)], "退款总额_分") if not after.empty else 0
        sales, refunds, spend = _sum(orders, "实收金额_分"), _sum(orders, "有效退款_分"), int(p.get("推广花费_分", 0))
        brush = _brush_amount(orders)
        accounted_sales = _sum(complete, "实收金额_分")
        accounted_net = accounted_sales - _sum(complete, "有效退款_分")
        contribution = _row_profit(complete) - spend
        cumulative_sales += sales; cumulative_profit += contribution
        rows.append({
            "日期": key, "已付款主订单数": int(orders["主订单编号"].nunique()) if not orders.empty else 0, "购买数量": _sum(orders, "购买数量_标准"),
            "销售额_分": sales, "订单批次成功退款_分": refunds, "期间退款完结金额_分": period_refund, "净销售额_分": sales - refunds,
            "刷单金额_分": brush, "真实销售额_分": _real_sales(sales, refunds, brush),
            "货品成本_分": _sum(normal_costed, "核算成本_分"), "运费_分": _sum(normal_costed, "核算运费_分"), "刷单成本_分": _sum(normal, "刷单成本_分"), "平台扣点_分": _sum(complete, "平台扣点_分"), "综合税赋_分": _sum(complete, "综合税赋_分"),
            "关闭已发货损失_分": _sum(closed, "关闭已发货损失_分"), "推广花费_分": spend, "推广归因成交金额_分": int(p.get("推广归因成交金额_分", 0)),
            "推广投产比": p.get("推广投产比"), "推广前经营利润_分": _row_profit(complete), "含推广经营贡献利润_分": contribution,
            "占期间销售比例": _optional_ratio(sales, total_sales), "累计销售额_分": cumulative_sales, "累计经营贡献利润_分": cumulative_profit,
            "成本率": _optional_ratio(_sum(normal_costed, "核算成本_分"), accounted_net),
            "运费率": _optional_ratio(_sum(normal_costed, "核算运费_分"), accounted_net),
            "平台费率": _optional_ratio(_sum(complete, "平台扣点_分"), accounted_net),
            "税费率": _optional_ratio(_sum(complete, "综合税赋_分"), accounted_net),
            "推广费率": _optional_ratio(spend, accounted_net),
            "核算覆盖率": _optional_ratio(accounted_sales, sales), "退款率": _optional_ratio(refunds, sales), "经营贡献利润率": _optional_ratio(contribution, accounted_net),
        })
        day += timedelta(days=1)
    return pd.DataFrame(rows)


def build_sku_report(profit: ProfitResult) -> pd.DataFrame:
    paid = _paid(profit)
    if paid.empty: return pd.DataFrame()
    rows = []
    for code, group in paid.groupby("商家编码", sort=True):
        complete = group[group["核算状态"] == "已核算"]
        rows.append({"商家编码": code, "产品名称": _link_product_name(group), "订单行数": len(group), "购买数量": _sum(group, "购买数量_标准"), "销售额_分": _sum(group, "实收金额_分"), "经营贡献利润_分": _row_profit(complete), "成本运费缺失行数": int((group["核算状态"] != "已核算").sum())})
    return pd.DataFrame(rows)


def build_summary(profit: ProfitResult, promotion: PromotionResult, links: pd.DataFrame, config: RunConfig) -> dict[str, object]:
    paid = _paid(profit); complete = paid[paid["核算状态"] == "已核算"] if not paid.empty else paid
    normal = complete[complete["订单类型"] == "正常订单"] if not complete.empty else complete
    normal_costed = _non_brush(normal)
    closed = complete[complete["订单类型"] == "付款后关闭已发货"] if not complete.empty else complete
    metrics = _promotion_metrics(promotion.detail)
    sales, accounted = _sum(paid, "实收金额_分"), _sum(complete, "实收金额_分")
    refunds, spend = _sum(paid, "有效退款_分"), int(metrics["推广花费_分"])
    brush = _brush_amount(paid)
    accounted_refunds = _sum(complete, "有效退款_分")
    accounted_net = accounted - accounted_refunds
    pre_profit = _row_profit(complete); contribution = pre_profit - spend
    paid_orders = int(paid["主订单编号"].nunique()) if not paid.empty else 0
    refunded_orders = int(paid.loc[paid["有效退款_分"] > 0, "主订单编号"].nunique()) if not paid.empty else 0
    closed_orders = int(paid.loc[paid["订单类型"] != "正常订单", "主订单编号"].nunique()) if not paid.empty else 0
    closed_shipped_orders = int(paid.loc[paid["订单类型"] == "付款后关闭已发货", "主订单编号"].nunique()) if not paid.empty else 0
    accountable_links = links[links["成本运费缺失行数"] == 0] if not links.empty else links
    summary: dict[str, object] = {
        "平台": config.platform.value, "平台扣点率": config.platform_fee_rate, "综合税赋率": config.tax_rate,
        "已付款销售额_分": sales, "订单批次成功退款金额_分": refunds, "期间退款完结金额_分": _sum(profit.period_completed_refunds, "退款总额_分"), "净销售额_分": sales - refunds,
        "刷单金额_分": brush, "真实销售额_分": _real_sales(sales, refunds, brush),
        "已核算销售额_分": accounted, "已核算订单批次成功退款_分": accounted_refunds, "已核算货品成本_分": _sum(normal_costed, "核算成本_分"), "已核算运费_分": _sum(normal_costed, "核算运费_分"), "已核算刷单成本_分": _sum(normal, "刷单成本_分"),
        "已核算平台扣点_分": _sum(complete, "平台扣点_分"), "已核算综合税赋_分": _sum(complete, "综合税赋_分"), "关闭已发货损失_分": _sum(closed, "关闭已发货损失_分"),
        "推广花费_分": spend, "推广归因成交金额_分": int(metrics["推广归因成交金额_分"]), "推广投产比": metrics["推广投产比"], "推广前经营利润_分": pre_profit,
        "含推广经营贡献利润_分": contribution, "经营贡献利润率": _optional_ratio(contribution, accounted_net), "销售额核算覆盖率": _optional_ratio(accounted, sales),
        "订单批次退款率": _optional_ratio(refunds, sales), "退款订单率": _optional_ratio(refunded_orders, paid_orders),
        "付款后关闭率": _optional_ratio(closed_orders, paid_orders), "关闭已发货率": _optional_ratio(closed_shipped_orders, paid_orders),
        "明细行核算覆盖率": _optional_ratio(len(complete), len(paid)), "成本运费缺失行数": profit.incomplete_rows,
        "已付款主订单数": paid_orders, "退款主订单数": refunded_orders, "付款后关闭主订单数": closed_orders, "关闭已发货主订单数": closed_shipped_orders, "购买数量": _sum(paid, "购买数量_标准"),
        "有效商品链接": len(links), "盈利链接数": int((accountable_links["含推广经营贡献利润_分"] > 0).sum()) if not accountable_links.empty else 0, "亏损链接数": int((accountable_links["含推广经营贡献利润_分"] <= 0).sum()) if not accountable_links.empty else 0,
        "订单+推广链接": int((links["数据覆盖"] == "订单+推广").sum()) if not links.empty else 0,
        "仅订单链接": int((links["数据覆盖"] == "仅订单").sum()) if not links.empty else 0,
        "仅推广链接": int((links["数据覆盖"] == "仅推广").sum()) if not links.empty else 0,
        "s_profit_share": config.s_profit_share, "a_profit_share": config.a_profit_share,
    }
    for grade in ("S", "A", "B", "C"):
        summary[f"{grade}链接数"] = int(links["SABC等级"].map(str).str.endswith(grade).sum()) if not links.empty else 0
    summary["待核算链接数"] = int((links["SABC等级"] == "待核算").sum()) if not links.empty else 0
    return summary


def build_analysis(profit: ProfitResult, promotion: PromotionResult, config: RunConfig, *, provisional: bool = False) -> AnalysisResult:
    links = build_link_report(profit, promotion, config, provisional=provisional)
    products = build_product_report(profit, promotion, links)
    daily = build_daily_report(profit, promotion, config)
    return AnalysisResult(profit, promotion, links, build_sku_report(profit), build_summary(profit, promotion, links, config), daily, products, tuple(profit.issues) + tuple(promotion.issues))
