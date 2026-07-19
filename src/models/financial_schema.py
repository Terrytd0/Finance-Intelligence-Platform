"""Data model for the ingestion pipeline.

Mirrors the contract defined in docs/data_schema.md. Keep the two in sync
when either changes.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

VALID_CATEGORIES = {"revenue", "expense", "budget"}

REQUIRED_TRANSACTION_FIELDS = (
    "transaction_id",
    "client_id",
    "date",
    "category",
    "amount",
)

REQUIRED_CLIENT_FIELDS = (
    "client_id",
    "client_name",
    "active",
)


@dataclass(frozen=True)
class Transaction:
    """Represents one validated financial transaction."""

    transaction_id: str
    client_id: str
    date: date
    category: str
    amount: Decimal
    currency: str
    description: str = ""


@dataclass(frozen=True)
class Client:
    client_id: str
    client_name: str
    active: bool
    region: str = ""
