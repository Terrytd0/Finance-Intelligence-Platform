"""Builds the prompt sent to the AI layer's anomaly detector.

This module only formats data that has already been computed by
src/analytics/kpi_engine.py into text. It performs no financial
calculations of its own -- every figure it renders is read directly from
the supplied FinancialKPIs / Transaction objects.
"""
from decimal import Decimal

from src.analytics.kpi_engine import FinancialKPIs
from src.models.financial_schema import Transaction

# Caps how many rows the full transaction ledger renders, so a large batch
# doesn't blow up the prompt size. Purely a formatting limit, not a
# business rule.
MAX_LEDGER_TRANSACTIONS = 200


def build_anomaly_prompt(kpis: FinancialKPIs, transactions: list[Transaction]) -> str:
    """Builds a structured prompt asking an LLM to reason over `kpis` and
    `transactions` and identify financial anomalies.

    The LLM is instructed to only reason from the data included in the
    prompt and to never invent or recompute figures.
    """
    sections = [
        _build_title(),
        _build_context_section(transactions),
        _build_key_kpis_section(kpis),
        _build_revenue_by_client_section(kpis),
        _build_expense_breakdown_section(kpis),
        _build_monthly_totals_section(kpis),
        _build_largest_transactions_section(kpis),
        _build_transaction_ledger_section(transactions),
        _build_instructions_section(),
        _build_response_format_section(),
    ]
    return "\n\n".join(sections)


def _build_title() -> str:
    return "FINANCIAL ANOMALY ANALYSIS REQUEST"


def _build_context_section(transactions: list[Transaction]) -> str:
    return (
        "## Executive Summary Context\n"
        "You are a financial analyst assistant supporting a finance team. "
        "All figures below were computed deterministically by the "
        "platform's analytics engine from validated transaction records "
        "and must be treated as ground truth. "
        f"This batch covers {len(transactions)} transaction(s). "
        "Do not recalculate, estimate, or invent any number that is not "
        "explicitly present in this prompt."
    )


def _build_key_kpis_section(kpis: FinancialKPIs) -> str:
    lines = [
        f"- Total Revenue: {_format_currency(kpis.total_revenue)}",
        f"- Total Expenses: {_format_currency(kpis.total_expenses)}",
        f"- Net Profit: {_format_currency(kpis.net_profit)}",
    ]
    return "## Key KPIs\n" + "\n".join(lines)


def _build_revenue_by_client_section(kpis: FinancialKPIs) -> str:
    return "## Revenue by Client\n" + _format_amount_table(kpis.revenue_by_client)


def _build_expense_breakdown_section(kpis: FinancialKPIs) -> str:
    return "## Expense Breakdown\n" + _format_amount_table(kpis.expenses_by_category)


def _build_monthly_totals_section(kpis: FinancialKPIs) -> str:
    return "## Monthly Totals\n" + _format_amount_table(kpis.monthly_totals)


def _build_largest_transactions_section(kpis: FinancialKPIs) -> str:
    return "## Largest Transactions\n" + _format_transaction_lines(
        kpis.largest_transactions
    )


def _build_transaction_ledger_section(transactions: list[Transaction]) -> str:
    ledger = transactions[:MAX_LEDGER_TRANSACTIONS]
    body = _format_transaction_lines(ledger)
    if len(transactions) > MAX_LEDGER_TRANSACTIONS:
        body += (
            f"\n(truncated: showing {MAX_LEDGER_TRANSACTIONS} of "
            f"{len(transactions)} transactions)"
        )
    return "## Full Transaction Ledger\n" + body


def _build_instructions_section() -> str:
    tasks = [
        "Identify unusual spending.",
        "Identify unusual revenue patterns.",
        "Identify concentration risks (e.g. overreliance on one client or "
        "expense category).",
        "Identify unusually large transactions.",
        "Identify other financial risks visible in the data.",
        "Provide clear, actionable recommendations for each finding.",
    ]
    rules = [
        "Never invent numbers -- use only the figures supplied above.",
        "Only reason from the supplied data; do not assume unstated facts.",
        "If there is not enough data to support a finding, do not report it.",
    ]
    lines = ["## Instructions", "Using only the data above:"]
    lines += [f"{i}. {task}" for i, task in enumerate(tasks, start=1)]
    lines.append("Rules:")
    lines += [f"- {rule}" for rule in rules]
    return "\n".join(lines)


def _build_response_format_section() -> str:
    return (
        "## Response Format\n"
        "Respond with ONLY valid JSON matching exactly this schema, and "
        "no other text, commentary, or markdown fences:\n"
        "{\n"
        '  "executive_summary": "string",\n'
        '  "anomalies": [\n'
        "    {\n"
        '      "severity": "low | medium | high | critical",\n'
        '      "title": "string",\n'
        '      "description": "string",\n'
        '      "evidence": "string",\n'
        '      "recommendation": "string"\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def _format_currency(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _format_amount_table(rows: dict[str, Decimal]) -> str:
    if not rows:
        return "(none)"
    return "\n".join(f"- {label}: {_format_currency(amount)}" for label, amount in rows.items())


def _format_transaction_lines(transactions: list[Transaction]) -> str:
    if not transactions:
        return "(none)"
    return "\n".join(_format_transaction_line(t) for t in transactions)


def _format_transaction_line(transaction: Transaction) -> str:
    return (
        f"- {transaction.transaction_id} | {transaction.date.isoformat()} | "
        f"client={transaction.client_id} | {transaction.category} | "
        f"{transaction.description or '(no description)'} | "
        f"{_format_currency(transaction.amount)} {transaction.currency}"
    )
