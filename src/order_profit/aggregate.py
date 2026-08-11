"""推广、订单、SKU、商品链接和期间汇总。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from order_profit.config import RunConfig
from order_profit.errors import NormalizationError
from order_profit.inputs import LoadedTable
from order_profit.models import Issue, Severity, SourceLocation
from order_profit.profit import ProfitResult


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
    summary: dict[str, int | Decimal | str]
    issues: tuple[Issue, ...] = ()


def _ratio(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) if denominator else Decimal("0")


def _promotion_metrics(frame: pd.DataFrame) -> dict[str, int | Decimal | str]:
    impressions = int(frame["展现量_标准"].sum()) if not frame.empty else 0
    clicks = int(frame["点击量_标准"].sum()) if not frame.empty else 0
    spend = int(frame["花费_分"].sum()) if not frame.empty else 0
    attributed = int(frame["总成交金额_分"].sum()) if not frame.empty else 0
    transactions = int(frame["总成交笔数_标准"].sum()) if not frame.empty else 0
    zero_denominators: list[str] = []
    if spend == 0:
        zero_denominators.append("推广ROI")
    if clicks == 0:
        zero_denominators.append("平均点击花费")
    if impressions == 0:
        zero_denominators.append("点击率")
    return {
        "推广展现量": impressions,
        "推广点击量": clicks,
        "推广花费_分": spend,
        "推广归因成交金额_分": attributed,
        "推广成交笔数": transactions,
        "推广ROI": _ratio(attributed, spend),
        "平均点击花费_分": _ratio(spend, clicks),
        "点击率": _ratio(clicks, impressions),
        "零分母状态": "、".join(zero_denominators),
    }


def _aggregate_promotion_frame(detail: pd.DataFrame, group_column: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for key, group in detail.groupby(group_column, sort=True, dropna=False):
        row: dict[str, object] = {group_column: key}
        row.update(_promotion_metrics(group))
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_promotion(
    promotion: LoadedTable | None,
    config: RunConfig,
) -> PromotionResult:
    if promotion is None:
        empty = pd.DataFrame()
        return PromotionResult(empty, empty, empty, empty)

    data = promotion.data.copy()
    start, end_exclusive = config.period_bounds()
    in_period_mask = data["日期_标准"].map(lambda value: start <= value < end_exclusive)
    detail = data.loc[in_period_mask].copy()
    out_of_period = data.loc[~in_period_mask].copy()

    empty_id = detail["主体ID"].eq("")
    if empty_id.any():
        row = detail.loc[empty_id].iloc[0]
        issue = Issue(
            code="PROMOTION_SUBJECT_ID_REQUIRED",
            severity=Severity.ERROR,
            message="期间内推广数据主体ID不能为空",
            location=SourceLocation(
                file=str(promotion.metadata.path),
                row=int(row["source_row_number"]),
                field="主体ID",
            ),
            suggestion="请从推广平台重新导出包含主体ID的报表",
        )
        raise NormalizationError(issue.message, code=issue.code, issues=[issue])

    if not detail.empty:
        detail["推广日期"] = detail["日期_标准"].map(lambda value: value.date().isoformat())
    daily = _aggregate_promotion_frame(detail, "推广日期") if not detail.empty else pd.DataFrame()
    products = _aggregate_promotion_frame(detail, "主体ID") if not detail.empty else pd.DataFrame()
    if not products.empty:
        latest_names = (
            detail.sort_values(["日期_标准", "source_row_number"])
            .drop_duplicates("主体ID", keep="last")
            .set_index("主体ID")["主体名称"]
        )
        products["主体名称"] = products["主体ID"].map(latest_names)
    return PromotionResult(
        detail=detail,
        out_of_period=out_of_period,
        daily=daily,
        products=products,
        issues=promotion.issues,
    )


def _latest_order_titles(profit: ProfitResult) -> dict[str, str]:
    frames = [profit.normal, profit.closed_shipped]
    orders = pd.concat(frames, ignore_index=True)
    if orders.empty:
        return {}
    selected = (
        orders.sort_values(["订单付款时间_标准", "source_row_number"])
        .drop_duplicates("商品ID", keep="last")
    )
    return dict(zip(selected["商品ID"].map(str), selected["商品标题"].map(str), strict=True))


def _sum_column(frame: pd.DataFrame, column: str) -> int:
    return int(frame[column].sum()) if not frame.empty else 0


def _groups_by_product(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if frame.empty:
        return {}
    product_ids = frame["商品ID"].map(str)
    return {
        product_id: frame.loc[index].copy()
        for product_id, index in product_ids.groupby(product_ids).groups.items()
    }


def build_link_report(profit: ProfitResult, promotion: PromotionResult) -> pd.DataFrame:
    normal_groups = _groups_by_product(profit.normal)
    closed_groups = _groups_by_product(profit.closed_shipped)
    order_ids = set(normal_groups) | set(closed_groups)
    promotion_ids = set(promotion.detail["主体ID"].map(str)) if not promotion.detail.empty else set()
    link_ids = sorted(order_ids | promotion_ids)
    order_titles = _latest_order_titles(profit)
    promotion_by_id = (
        promotion.products.set_index("主体ID").to_dict("index") if not promotion.products.empty else {}
    )
    rows: list[dict[str, object]] = []
    empty_normal = profit.normal.iloc[0:0]
    empty_closed = profit.closed_shipped.iloc[0:0]
    for product_id in link_ids:
        normal = normal_groups.get(product_id, empty_normal)
        closed = closed_groups.get(product_id, empty_closed)
        promo = promotion_by_id.get(product_id, {})
        has_order = product_id in order_ids
        has_promotion = product_id in promotion_ids
        coverage = "订单+推广" if has_order and has_promotion else ("仅订单" if has_order else "仅推广")
        normal_complete = normal[normal["核算状态"] == "已核算"]
        closed_complete = closed[closed["核算状态"] == "已核算"]
        normal_profit = int(normal_complete["正常订单利润_分"].sum()) if not normal_complete.empty else 0
        closed_loss = (
            int(closed_complete["关闭已发货损失_分"].sum()) if not closed_complete.empty else 0
        )
        promo_spend = int(promo.get("推广花费_分", 0))
        incomplete = int((normal["核算状态"] != "已核算").sum()) + int(
            (closed["核算状态"] != "已核算").sum()
        )
        all_sales = int(normal["实收金额_分"].sum()) if not normal.empty else 0
        all_refunds = int(normal["有效退款_分"].sum()) if not normal.empty else 0
        attributed = int(promo.get("推广归因成交金额_分", 0))
        roi = promo.get("推广ROI", Decimal("0"))
        link_profit = normal_profit - closed_loss - promo_spend
        action_tags: list[str] = []
        if incomplete:
            action_tags.append("补成本/运费")
        if not has_order and has_promotion:
            action_tags.append("检查仅推广无订单")
        if has_order and not has_promotion:
            action_tags.append("完善推广覆盖")
        high_refund = (
            all_refunds > 0
            and all_sales > 0
            and Decimal(all_refunds) / Decimal(all_sales) >= Decimal("0.1")
        )
        if high_refund:
            action_tags.append("检查售后退款")
        if closed_loss > 0:
            action_tags.append("复核关闭发货损失")
        if has_promotion and link_profit < 0:
            action_tags.append("降投/停投复核")
        elif has_promotion and link_profit > 0 and Decimal(str(roi)) >= Decimal("2"):
            action_tags.append("加投观察")
        if not action_tags:
            action_tags.append("保持观察")
        action_priority = (
            "高"
            if incomplete or high_refund or (has_promotion and link_profit < 0)
            else ("中" if action_tags != ["保持观察"] else "低")
        )
        title = order_titles.get(product_id) or str(promo.get("主体名称", ""))
        rows.append(
            {
                "商品ID": product_id,
                "商品链接": f"https://item.taobao.com/item.htm?id={product_id}",
                "商品标题": title,
                "数据覆盖": coverage,
                "正常订单行数": len(normal),
                "关闭已发货行数": len(closed),
                "正常主订单数": normal["主订单编号"].nunique(),
                "正常购买数量": int(normal["购买数量_标准"].sum()) if not normal.empty else 0,
                "关闭购买数量": int(closed["购买数量_标准"].sum()) if not closed.empty else 0,
                "全部销售额_分": all_sales,
                "已核算销售额_分": int(normal_complete["实收金额_分"].sum()) if not normal_complete.empty else 0,
                "全部有效退款_分": int(normal["有效退款_分"].sum()) if not normal.empty else 0,
                "已核算有效退款_分": int(normal_complete["有效退款_分"].sum()) if not normal_complete.empty else 0,
                "正常订单货品成本_分": _sum_column(normal_complete, "核算成本_分"),
                "正常订单运费_分": _sum_column(normal_complete, "核算运费_分"),
                "平台扣点_分": _sum_column(normal_complete, "平台扣点_分"),
                "综合税赋_分": _sum_column(normal_complete, "综合税赋_分"),
                "正常订单利润_分": normal_profit,
                "关闭已发货损失_分": closed_loss,
                "推广展现量": int(promo.get("推广展现量", 0)),
                "推广点击量": int(promo.get("推广点击量", 0)),
                "推广花费_分": promo_spend,
                "推广归因成交金额_分": attributed,
                "推广成交笔数": int(promo.get("推广成交笔数", 0)),
                "推广ROI": roi,
                "含推广利润_分": link_profit,
                "盈利状态": "盈利" if link_profit > 0 else ("亏损" if link_profit < 0 else "持平"),
                "成本运费缺失行数": incomplete,
                "核算状态": "暂算" if incomplete else "完整",
                "运营动作优先级": action_priority,
                "运营动作": "、".join(action_tags),
            }
        )
    return pd.DataFrame(rows)


def build_sku_report(profit: ProfitResult) -> pd.DataFrame:
    frames = []
    if not profit.normal.empty:
        normal = profit.normal.copy()
        normal["订单类型"] = "正常"
        frames.append(normal)
    if not profit.closed_shipped.empty:
        closed = profit.closed_shipped.copy()
        closed["订单类型"] = "关闭已发货"
        frames.append(closed)
    if not frames:
        return pd.DataFrame()
    data = pd.concat(frames, ignore_index=True)
    rows: list[dict[str, object]] = []
    for code, group in data.groupby("商家编码", sort=True):
        normal = group[group["订单类型"] == "正常"]
        closed = group[group["订单类型"] == "关闭已发货"]
        normal_complete = normal[normal["核算状态"] == "已核算"]
        closed_complete = closed[closed["核算状态"] == "已核算"]
        rows.append(
            {
                "商家编码": code,
                "正常订单行数": len(normal),
                "关闭已发货行数": len(closed),
                "购买数量": int(group["购买数量_标准"].sum()),
                "全部销售额_分": _sum_column(normal, "实收金额_分"),
                "正常订单利润_分": _sum_column(normal_complete, "正常订单利润_分"),
                "关闭已发货损失_分": _sum_column(closed_complete, "关闭已发货损失_分"),
                "成本运费缺失行数": int((group["核算状态"] != "已核算").sum()),
            }
        )
    return pd.DataFrame(rows)


def build_summary(
    profit: ProfitResult,
    promotion: PromotionResult,
    links: pd.DataFrame,
    config: RunConfig,
) -> dict[str, int | Decimal | str]:
    normal = profit.normal
    normal_complete = normal[normal["核算状态"] == "已核算"]
    closed_complete = profit.closed_shipped[
        profit.closed_shipped["核算状态"] == "已核算"
    ]
    promotion_metrics = _promotion_metrics(promotion.detail)
    normal_profit = (
        int(normal_complete["正常订单利润_分"].sum()) if not normal_complete.empty else 0
    )
    closed_loss = (
        int(closed_complete["关闭已发货损失_分"].sum()) if not closed_complete.empty else 0
    )
    spend = int(promotion_metrics["推广花费_分"])
    net_profit = normal_profit - closed_loss - spend
    accounted_sales = (
        int(normal_complete["实收金额_分"].sum()) if not normal_complete.empty else 0
    )
    incomplete = profit.incomplete_rows
    return {
        "平台": config.platform.value,
        "正常订单行数": len(normal),
        "关闭已发货行数": len(profit.closed_shipped),
        "全部有编码销售额_分": int(normal["实收金额_分"].sum()) if not normal.empty else 0,
        "已核算销售额_分": accounted_sales,
        "全部有效退款_分": int(normal["有效退款_分"].sum()) if not normal.empty else 0,
        "已核算有效退款_分": _sum_column(normal_complete, "有效退款_分"),
        "已核算货品成本_分": _sum_column(normal_complete, "核算成本_分"),
        "已核算运费_分": _sum_column(normal_complete, "核算运费_分"),
        "已核算平台扣点_分": _sum_column(normal_complete, "平台扣点_分"),
        "已核算综合税赋_分": _sum_column(normal_complete, "综合税赋_分"),
        "正常订单已核算利润_分": normal_profit,
        "关闭已发货损失_分": closed_loss,
        "推广花费_分": spend,
        "推广归因成交金额_分": int(promotion_metrics["推广归因成交金额_分"]),
        "推广前经营利润_分": normal_profit - closed_loss,
        "含推广净利润_分": net_profit,
        "含推广净利率": _ratio(net_profit, accounted_sales),
        "成本运费缺失行数": incomplete,
        "有效商品链接": len(links),
        "订单+推广链接": int((links["数据覆盖"] == "订单+推广").sum()) if not links.empty else 0,
        "仅订单链接": int((links["数据覆盖"] == "仅订单").sum()) if not links.empty else 0,
        "仅推广链接": int((links["数据覆盖"] == "仅推广").sum()) if not links.empty else 0,
    }


def build_analysis(profit: ProfitResult, promotion: PromotionResult, config: RunConfig) -> AnalysisResult:
    links = build_link_report(profit, promotion)
    sku = build_sku_report(profit)
    summary = build_summary(profit, promotion, links, config)
    return AnalysisResult(
        profit=profit,
        promotion=promotion,
        links=links,
        sku=sku,
        summary=summary,
        issues=tuple(profit.issues) + tuple(promotion.issues),
    )
