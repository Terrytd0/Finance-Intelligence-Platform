"""Deterministic KPI calculations for the KPI Engine step in
docs/architecture.md. Business logic only, no AI: every figure here must be
reproducible from the transaction data alone.

Only `category == "revenue"` and `category == "expense"` rows are actual
money movements; `budget` rows are planned figures (docs/data_schema.md) and
are excluded from every total below except `largest_transactions`, where a
large planned budget line is still worth surfacing.
"""
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from src.models.financial_schema import Transaction

REVENUE = "revenue"
EXPENSE = "expense"


@dataclass(frozen=True)
class FinancialKPIs:
    """Snapshot of deterministic financial metrics for one batch of
    transactions."""

    total_revenue: Decimal
    total_expenses: Decimal
    net_profit: Decimal
    revenue_by_client: dict[str, Decimal]
    expenses_by_category: dict[str, Decimal]
    monthly_totals: dict[str, Decimal]
    largest_transactions: list[Transaction]


def generate_kpis(transactions: list[Transaction], *, top_n: int = 5) -> FinancialKPIs:
    """Computes FinancialKPIs from validated, cleaned transactions.

    `top_n` caps how many rows `largest_transactions` holds, ranked by
    absolute amount across all categories.
    """
    revenue_transactions = [t for t in transactions if t.category == REVENUE]
    expense_transactions = [t for t in transactions if t.category == EXPENSE]

    total_revenue = _sum_amounts(revenue_transactions)
    # amount is negative for expense outflows (docs/data_schema.md); negate
    # so total_expenses reads as the positive figure the business expects.
    total_expenses = -_sum_amounts(expense_transactions)
    net_profit = total_revenue - total_expenses

    return FinancialKPIs(
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        net_profit=net_profit,
        revenue_by_client=_group_by_sum(revenue_transactions, key=lambda t: t.client_id),
        expenses_by_category=_expenses_by_category(expense_transactions),
        monthly_totals=_monthly_totals(revenue_transactions + expense_transactions),
        largest_transactions=_largest_transactions(transactions, top_n),
    )


def _sum_amounts(transactions: list[Transaction]) -> Decimal:
    return sum((t.amount for t in transactions), Decimal("0"))


def _group_by_sum(
    transactions: list[Transaction], *, key: Callable[[Transaction], str]
) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for transaction in transactions:
        totals[key(transaction)] += transaction.amount
    return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))


def _expenses_by_category(expense_transactions: list[Transaction]) -> dict[str, Decimal]:
    # The schema has no dedicated expense-category column -- `category`
    # only distinguishes revenue/expense/budget. Until one is added,
    # `description` (e.g. "Office lease", "Software licensing") is the
    # closest available grouping for expenses.
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for transaction in expense_transactions:
        label = transaction.description or "uncategorized"
        totals[label] += -transaction.amount
    return dict(sorted(totals.items(), key=lambda item: item[1], reverse=True))


def _monthly_totals(actual_transactions: list[Transaction]) -> dict[str, Decimal]:
    # Net (revenue - expenses) per calendar month, keyed "YYYY-MM" and
    # sorted chronologically; budget rows are excluded (see module docstring).
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for transaction in actual_transactions:
        month_key = transaction.date.strftime("%Y-%m")
        totals[month_key] += transaction.amount
    return dict(sorted(totals.items()))


def _largest_transactions(transactions: list[Transaction], top_n: int) -> list[Transaction]:
    return sorted(transactions, key=lambda t: abs(t.amount), reverse=True)[:top_n]
