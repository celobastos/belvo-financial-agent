from __future__ import annotations

from decimal import Decimal

from .heuristics import money
from .models import ChartSpec


def group_chart(title: str, x_label: str, y_label: str, rows: list[dict], chart_type: str | None = "bar") -> ChartSpec | None:
    if len(rows) < 2:
        return None
    if chart_type not in {"bar", "pie"}:
        return None
    return ChartSpec(chart_type=chart_type, title=title, x_label=x_label, y_label=y_label, data=rows)


def account_spending_chart(groups: list[dict], chart_type: str | None = "bar") -> ChartSpec | None:
    rows = [
        {"Account": group["account"], "Total": float(Decimal(str(group["total"])))}
        for group in groups
        if money(group.get("total")) > 0
    ]
    return group_chart("Spending by account", "Account", "BRL", rows, chart_type)


def category_spending_chart(groups: list[dict], chart_type: str | None = "bar") -> ChartSpec | None:
    rows = [
        {"Category": group["category"], "Total": float(Decimal(str(group["total"])))}
        for group in groups
        if money(group.get("total")) > 0
    ]
    return group_chart("Spending by category", "Category", "BRL", rows, chart_type)


def subscription_breakdown_chart(groups: list[dict]) -> ChartSpec | None:
    rows = [
        {"Service": group["service"], "Total": float(Decimal(str(group["total"])))}
        for group in groups
        if money(group.get("total")) > 0
    ]
    return group_chart("Subscription spending by service", "Service", "BRL", rows, "bar")
