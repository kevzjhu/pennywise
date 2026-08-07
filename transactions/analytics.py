"""Aggregation and chart-shaping for the analytics dashboard.

Kept out of views.py so the view stays request/response plumbing and this
module stays testable without a request. Nothing here knows about HTML or CSS —
budget status is reported as a semantic name and the template picks the colour.
"""
import calendar
import datetime
from decimal import Decimal

from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear

CENTRAL_NODE = "Monthly Cash Pool"
DEFICIT_NODE = "Savings / Credit Drawdown"
SURPLUS_NODE = "Net Savings / Unspent"
UNCATEGORIZED = 'Uncategorized'

# Percent-of-budget thresholds. The template maps these names to colours.
OVER_BUDGET = 'over'
NEAR_BUDGET = 'warning'
UNDER_BUDGET = 'ok'
NEAR_BUDGET_THRESHOLD = 80


def total_amount(queryset):
    """Sum `amount` over `queryset`, returning 0 rather than None when empty."""
    return queryset.aggregate(
        total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
    )['total']


def budget_status(percent_used):
    if percent_used > 100:
        return OVER_BUDGET
    if percent_used >= NEAR_BUDGET_THRESHOLD:
        return NEAR_BUDGET
    return UNDER_BUDGET


def spend_by_category(expense_qs):
    """Map category id -> total spend in one grouped query."""
    return {
        row['category']: row['total']
        for row in expense_qs.values('category').annotate(
            total=Coalesce(Sum('amount'), Value(0), output_field=DecimalField())
        )
    }


def budget_for_period(category, history_records, target_years, target_months):
    """Sum the budget that was in force for each month in the selected period.

    `history_records` must be ascending by effective_start_date; the latest
    record starting on or before a month's end is the one in force that month.
    """
    total = Decimal('0.00')
    for year in target_years:
        for month in target_months:
            month_end = datetime.date(year, month, calendar.monthrange(year, month)[1])
            active_budget = category.monthly_budget
            for record in history_records:
                if record.effective_start_date <= month_end:
                    active_budget = record.amount
                else:
                    break
            total += active_budget
    return total


def build_budget_progress(categories_qs, expense_qs, target_years, target_months):
    """Per-category spend vs budget, plus the chart series and the overall total."""
    spend_lookup = spend_by_category(expense_qs)

    labels, spend_series, budget_series, progress = [], [], [], []
    total_budget = Decimal('0.00')

    for category in categories_qs:
        spend = spend_lookup.get(category.id, Decimal('0.00'))
        # sorted() over the prefetched cache — .order_by() would re-query per category
        history = sorted(category.budget_history.all(), key=lambda r: r.effective_start_date)
        budget = budget_for_period(category, history, target_years, target_months)

        total_budget += budget
        if budget > 0:
            percent_used = float(spend / budget * 100)
        else:
            percent_used = 100.0 if spend > 0 else 0.0

        labels.append(category.name)
        spend_series.append(float(spend))
        budget_series.append(float(budget))
        progress.append({
            'name': category.name,
            'spend': spend,
            'budget': budget,
            'percent': min(percent_used, 100),
            'raw_percent': percent_used,
            'status': budget_status(percent_used),
        })

    uncategorized = total_amount(expense_qs.filter(category__isnull=True))
    if uncategorized > 0:
        labels.append(UNCATEGORIZED)
        spend_series.append(float(uncategorized))
        budget_series.append(0.0)

    return {
        'cat_labels': labels,
        'cat_spend': spend_series,
        'cat_budgets': budget_series,
        'budget_progress_list': progress,
        'total_budget': total_budget,
    }


def build_monthly_trends(expense_qs, income_qs):
    """Aligned month-by-month spend and income series for the trend chart."""

    def by_month(queryset):
        rows = (
            queryset.annotate(year=ExtractYear('date'), month=ExtractMonth('date'))
            .values('year', 'month')
            .annotate(total=Sum('amount'))
        )
        return {(row['year'], row['month']): float(row['total']) for row in rows}

    expense_map = by_month(expense_qs)
    income_map = by_month(income_qs)

    months = sorted(set(expense_map) | set(income_map))
    return {
        'trend_labels': [f"{calendar.month_abbr[month]} {year}" for year, month in months],
        'trend_spend': [expense_map.get(key, 0.0) for key in months],
        'trend_income': [income_map.get(key, 0.0) for key in months],
    }


def build_sankey_flows(expense_qs, income_qs, total_spend, total_income):
    """Cash-flow edges: income sources -> pool -> spend categories."""
    flows = []

    for row in income_qs.values('source_name').annotate(total=Sum('amount')):
        amount = float(row['total'] or 0)
        if amount > 0:
            flows.append({'from': row['source_name'], 'to': CENTRAL_NODE, 'flow': amount})

    if total_spend > total_income:
        flows.append({
            'from': DEFICIT_NODE,
            'to': CENTRAL_NODE,
            'flow': float(total_spend - total_income),
        })

    for row in expense_qs.values('category__name').annotate(total=Sum('amount')):
        amount = float(row['total'] or 0)
        if amount > 0:
            flows.append({
                'from': CENTRAL_NODE,
                'to': row['category__name'] or UNCATEGORIZED,
                'flow': amount,
            })

    if total_income > total_spend:
        flows.append({
            'from': CENTRAL_NODE,
            'to': SURPLUS_NODE,
            'flow': float(total_income - total_spend),
        })

    return flows
