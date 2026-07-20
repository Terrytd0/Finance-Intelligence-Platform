from datetime import date
from decimal import Decimal

from src.ai.prompt_builder import MAX_LEDGER_TRANSACTIONS, build_anomaly_prompt
from src.analytics.kpi_engine import FinancialKPIs, generate_kpis
from src.models.financial_schema import Transaction


def _transaction(
    transaction_id: str,
    client_id: str,
    date_str: str,
    category: str,
    amount: str,
    description: str = "",
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        client_id=client_id,
        date=date.fromisoformat(date_str),
        category=category,
        amount=Decimal(amount),
        currency="USD",
        description=description,
    )


def _synthetic_transactions(count: int) -> list[Transaction]:
    return [
        _transaction(f"T{i:04d}", "C001", "2026-01-01", "revenue", "100.00", "synthetic")
        for i in range(1, count + 1)
    ]


TRANSACTIONS = [
    _transaction("T1", "C001", "2026-01-05", "revenue", "125000.00", "Advisory fee"),
    _transaction("T2", "C001", "2026-01-12", "expense", "-8500.00", "Office lease"),
    _transaction("T3", "C002", "2026-01-15", "revenue", "64200.50", "Management fee"),
    _transaction("T4", "C002", "2026-01-20", "budget", "15000.00", "Q1 marketing budget"),
    _transaction("T5", "C001", "2026-02-01", "expense", "-3200.75", "Software licensing"),
    _transaction("T6", "C002", "2026-02-10", "revenue", "42000.00", "Performance fee"),
]

KPIS: FinancialKPIs = generate_kpis(TRANSACTIONS)
PROMPT = build_anomaly_prompt(KPIS, TRANSACTIONS)


def test_build_anomaly_prompt_returns_a_string():
    assert isinstance(PROMPT, str)
    assert len(PROMPT) > 0


def test_executive_summary_context_section_exists():
    assert "## Executive Summary Context" in PROMPT


def test_key_kpis_section_exists():
    assert "## Key KPIs" in PROMPT
    assert "Total Revenue" in PROMPT
    assert "Total Expenses" in PROMPT
    assert "Net Profit" in PROMPT


def test_monthly_totals_section_exists():
    assert "## Monthly Totals" in PROMPT


def test_expense_breakdown_section_exists():
    assert "## Expense Breakdown" in PROMPT


def test_largest_transactions_section_exists():
    assert "## Largest Transactions" in PROMPT


def test_transaction_ledger_section_exists_with_sample_ids():
    assert "## Full Transaction Ledger" in PROMPT
    for transaction in TRANSACTIONS:
        assert transaction.transaction_id in PROMPT


def test_json_response_schema_is_present():
    assert "## Response Format" in PROMPT
    for field in (
        "executive_summary",
        "anomalies",
        "severity",
        "title",
        "description",
        "evidence",
        "recommendation",
    ):
        assert field in PROMPT


def test_prompt_contains_key_instructions():
    assert "Respond with ONLY valid JSON" in PROMPT
    assert "Never invent numbers" in PROMPT
    assert "supplied data" in PROMPT


def test_empty_transaction_list_does_not_raise():
    empty_kpis = generate_kpis([])

    prompt = build_anomaly_prompt(empty_kpis, [])

    assert isinstance(prompt, str)
    assert "(none)" in prompt


def test_transaction_ledger_is_truncated_to_max_ledger_transactions():
    total = MAX_LEDGER_TRANSACTIONS + 10
    transactions = _synthetic_transactions(total)
    kpis = generate_kpis(transactions)

    prompt = build_anomaly_prompt(kpis, transactions)
    ledger_section = next(
        section for section in prompt.split("\n\n") if section.startswith("## Full Transaction Ledger")
    )

    assert ledger_section.count("\n- ") == MAX_LEDGER_TRANSACTIONS
    assert f"(truncated: showing {MAX_LEDGER_TRANSACTIONS} of {total} transactions)" in ledger_section
    assert transactions[0].transaction_id in ledger_section
    assert transactions[MAX_LEDGER_TRANSACTIONS - 1].transaction_id in ledger_section
    assert transactions[MAX_LEDGER_TRANSACTIONS].transaction_id not in ledger_section
    assert transactions[-1].transaction_id not in ledger_section


def test_currency_values_are_formatted_and_key_kpi_numbers_appear():
    assert f"${KPIS.total_revenue:,.2f}" in PROMPT
    assert f"${KPIS.total_expenses:,.2f}" in PROMPT
    assert f"${KPIS.net_profit:,.2f}" in PROMPT
    assert "$231,200.50" in PROMPT
    assert "$11,700.75" in PROMPT
    assert "$219,499.75" in PROMPT
