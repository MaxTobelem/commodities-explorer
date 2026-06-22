"""Portfolio simulation models (idea 1 — live trading sim).

A Portfolio is a per-user, **single-currency** (EUR *or* USD) cash+positions
ledger. Cash, positions and value are never stored — they are *replayed* from the
ordered Transaction journal (the single source of truth), which makes back-dating
and "as-of date" valuation trivial and keeps everything consistent.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models

from commodities.models import TimeStamped


class Portfolio(TimeStamped):
    class Currency(models.TextChoices):
        EUR = "EUR", "Euro"
        USD = "USD", "Dollar US"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portfolios"
    )
    name = models.CharField(max_length=120)
    # Single currency, chosen at creation and frozen once a transaction exists
    # (enforced in the API/service) — the journal must never mix currencies.
    base_currency = models.CharField(
        max_length=3, choices=Currency.choices, default=Currency.EUR
    )
    description = models.TextField(blank=True)
    # Broker fees, editable per portfolio. Default 0.20% + 0 fixed sits mid-range
    # among EU retail brokers (IBKR/DEGIRO ~0.05-0.10%, Boursorama ~0.5%,
    # Trade Republic 1€/order ≈ fee_fixed). fee_percent is a percent (0.20 = 0.20%).
    fee_percent = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("0.20"))
    fee_fixed = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    class Meta:
        ordering = ["name"]
        verbose_name = "portefeuille"
        verbose_name_plural = "portefeuilles"

    def __str__(self) -> str:
        return f"{self.name} ({self.base_currency})"

    @property
    def has_transactions(self) -> bool:
        return self.transactions.exists()


class Transaction(TimeStamped):
    """One ledger entry. Cash moves (deposit/withdraw) leave commodity/quantity/
    unit_price null; trades (buy/sell) carry them. `amount` is always the position
    value (buy/sell) or cash sum (deposit/withdraw) in the portfolio's currency;
    `fee` is charged on top. `unit_price` is snapshotted so the ledger is auditable."""

    class Kind(models.TextChoices):
        DEPOSIT = "deposit", "Dépôt"
        WITHDRAW = "withdraw", "Retrait"
        BUY = "buy", "Achat"
        SELL = "sell", "Vente"

    portfolio = models.ForeignKey(
        Portfolio, on_delete=models.CASCADE, related_name="transactions"
    )
    date = models.DateField()
    kind = models.CharField(max_length=8, choices=Kind.choices)
    commodity = models.ForeignKey(
        "commodities.Commodity",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    quantity = models.DecimalField(max_digits=24, decimal_places=8, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["date", "id"]  # chronological replay order
        verbose_name = "transaction"
        verbose_name_plural = "transactions"

    def __str__(self) -> str:
        label = self.get_kind_display()
        if self.commodity_id:
            return f"{label} {self.commodity} ({self.amount})"
        return f"{label} ({self.amount})"
