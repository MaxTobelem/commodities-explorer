"""Imported financial assets (idea 2 — historical backtest & risk).

A ``MarketAsset`` is a financial index (equities, bonds, hedge funds, CTA, cash…)
or an auxiliary series (CPI for inflation, FX for currency conversion). Its history
is stored as a plain dated ``AssetPrice`` series — base-100 index *levels*, monthly
today but the schema (one value per date) supports daily just as well, so a future
daily/paid provider plugs in without a model change.

These complement the physical ``commodities`` so a backtest can mix both universes.
"""

from __future__ import annotations

from django.db import models

from commodities.models import TimeStamped


class MarketAsset(TimeStamped):
    class AssetClass(models.TextChoices):
        EQUITY = "equity", "Actions"
        BOND = "bond", "Obligations"
        HIGH_YIELD = "high_yield", "High yield"
        HEDGE_FUND = "hedge_fund", "Hedge funds"
        CTA = "cta", "CTA / Managed futures"
        CASH = "cash", "Monétaire"
        CPI = "cpi", "Inflation (IPC)"
        FX = "fx", "Change"

    class Currency(models.TextChoices):
        EUR = "EUR", "Euro"
        USD = "USD", "Dollar US"

    code = models.CharField(max_length=24, unique=True, help_text="Ticker, ex. NDDUWI")
    name = models.CharField(max_length=120)
    asset_class = models.CharField(max_length=16, choices=AssetClass.choices)
    # Quote currency of the index returns (used to FX-convert into a backtest's
    # currency). CPI/FX are auxiliary and keep their natural currency.
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    source = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["asset_class", "name"]
        verbose_name = "actif financier"
        verbose_name_plural = "actifs financiers"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class AssetPrice(TimeStamped):
    """One dated index level (base 100). Monthly today, daily-ready."""

    asset = models.ForeignKey(MarketAsset, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    value = models.DecimalField(max_digits=18, decimal_places=6)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["asset", "date"], name="uniq_assetprice_asset_date"),
        ]
        indexes = [models.Index(fields=["asset", "date"])]

    def __str__(self) -> str:
        return f"{self.asset.code} @ {self.date}: {self.value}"
