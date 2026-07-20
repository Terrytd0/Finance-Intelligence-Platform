from datetime import date
from decimal import Decimal

from src.analytics.kpi_engine import generate_kpis
from src.models.financial_schema import Transaction


def _transaction(
    transaction_id,
    client_id,
    date_str,
    category,
    amount,
    description="",
):
    return Transaction(
        transaction_id=transaction_id,
        client_id=client_id,
        date=date.fromisoformat(date_str),
        category=category,
        amount=Decimal(amount),
        currency="USD",
        description=description,
    )


TRANSACTIONS = [
    _transaction("T1", "C001", "2026-01-05", "revenue", "125000.00", "Advisory fee"),
    _transaction("T2", "C001", "2026-01-12", "expense", "-8500.00", "Office lease"),
    _transaction("T3", "C002", "2026-01-15", "revenue", "64200.50", "Management fee"),
    _transaction("T4", "C002", "2026-01-20", "budget", "15000.00", "Q1 marketing budget"),
    _transaction("T5", "C001", "2026-02-01", "expense", "-3200.75", "Software licensing"),
    _transaction("T6", "C002", "2026-02-10", "revenue", "42000.00", "Performance fee"),
]


def test_totals_and_net_profit_exclude_budget():
    kpis = generate_kpis(TRANSACTIONS)

    assert kpis.total_revenue == Decimal("231200.50")
    assert kpis.total_expenses == Decimal("11700.75")
    assert kpis.net_profit == Decimal("219499.75")


def test_revenue_by_client_sums_per_client_descending():
    kpis = generate_kpis(TRANSACTIONS)

    assert list(kpis.revenue_by_client.items()) == [
        ("C001", Decimal("125000.00")),
        ("C002", Decimal("106200.50")),
    ]


def test_expenses_by_category_uses_description_as_grouping():
    kpis = generate_kpis(TRANSACTIONS)

    assert kpis.expenses_by_category == {
        "Office lease": Decimal("8500.00"),
        "Software licensing": Decimal("3200.75"),
    }


def test_monthly_totals_are_net_and_exclude_budget():
    kpis = generate_kpis(TRANSACTIONS)

    assert kpis.monthly_totals == {
        "2026-01": Decimal("180700.50"),
        "2026-02": Decimal("38799.25"),
    }


def test_largest_transactions_ranked_by_absolute_amount():
    kpis = generate_kpis(TRANSACTIONS, top_n=2)

    assert [t.transaction_id for t in kpis.largest_transactions] == ["T1", "T3"]


def test_empty_input_returns_zeroed_kpis():
    kpis = generate_kpis([])

    assert kpis.total_revenue == Decimal("0")
    assert kpis.total_expenses == Decimal("0")
    assert kpis.net_profit == Decimal("0")
    assert kpis.revenue_by_client == {}
    assert kpis.expenses_by_category == {}
    assert kpis.monthly_totals == {}
    assert kpis.largest_transactions == []
