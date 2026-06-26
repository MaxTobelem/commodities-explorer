"""Static metadata for the imported iMGP universe.

Maps each CSV ticker to its display name, asset class and quote currency. Names &
currencies are sourced from the iMGP fixture; ``EURBGN`` is the EUR/USD series
(USD per 1 EUR) used for FX conversion, ``USCPI``/``EUCPI`` drive inflation & the
real comparisons. The CSV files live under ``markets/seed/`` (copied from the
original ``dashboard-master`` export).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import MarketAsset

A = MarketAsset.AssetClass
C = MarketAsset.Currency


@dataclass(frozen=True)
class AssetMeta:
    code: str
    name: str
    asset_class: str
    currency: str
    path: str  # relative to markets/seed/


# Investable indices + cash + auxiliary (CPI, FX). The EUR-hedged (_HDG) variants
# are intentionally left out: FX conversion already lets a EUR backtest hold the
# USD series, so importing both would only duplicate exposure.
ASSETS: list[AssetMeta] = [
    # Equities (USD)
    AssetMeta("NDDUWI", "MSCI World", A.EQUITY, C.USD, "assets/NDDUWI.csv"),
    AssetMeta("NDUEACWF", "MSCI ACWI", A.EQUITY, C.USD, "assets/NDUEACWF.csv"),
    AssetMeta("NDDUEAFE", "MSCI EAFE", A.EQUITY, C.USD, "assets/NDDUEAFE.csv"),
    AssetMeta("M2EF", "MSCI Marchés émergents", A.EQUITY, C.USD, "assets/M2EF.csv"),
    AssetMeta("SPXT", "S&P 500 Total Return", A.EQUITY, C.USD, "assets/SPXT.csv"),
    AssetMeta("RU20INTR", "Russell 2000 Total Return", A.EQUITY, C.USD, "assets/RU20INTR.csv"),
    # Bonds
    AssetMeta("LBUSTRUU", "Bloomberg US Aggregate", A.BOND, C.USD, "assets/LBUSTRUU.csv"),
    AssetMeta("LUACTRUU", "Bloomberg US Corporate", A.BOND, C.USD, "assets/LUACTRUU.csv"),
    AssetMeta("LBUTTRUU", "Bloomberg US Treasury TIPS", A.BOND, C.USD, "assets/LBUTTRUU.csv"),
    AssetMeta("CVA0", "ICE BofA 1-5 ans US Corporate", A.BOND, C.USD, "assets/CVA0.csv"),
    AssetMeta("I02000US", "Bloomberg Euro Aggregate", A.BOND, C.EUR, "assets/I02000US.csv"),
    # High yield
    AssetMeta("H0A0", "ICE BofA US High Yield", A.HIGH_YIELD, C.USD, "assets/H0A0.csv"),
    # Hedge funds / CTA
    AssetMeta("HFRXGL", "HFRX Global Hedge Fund", A.HEDGE_FUND, C.USD, "assets/HFRXGL.csv"),
    AssetMeta("NEIXCTA", "SG CTA Index", A.CTA, C.USD, "assets/NEIXCTA.csv"),
    AssetMeta("NEIXCTAT", "SG Trend Index", A.CTA, C.USD, "assets/NEIXCTAT.csv"),
    # Cash (risk-free proxies)
    AssetMeta("SBWMUD1L", "Monétaire USD 1 mois", A.CASH, C.USD, "assets/SBWMUD1L.csv"),
    AssetMeta("SBWMEU1L", "Monétaire EUR 1 mois", A.CASH, C.EUR, "assets/SBWMEU1L.csv"),
    # Auxiliary: inflation & FX (not investable; used by the risk engine)
    AssetMeta("USCPI", "Inflation US (IPC)", A.CPI, C.USD, "inflation/USCPI.csv"),
    AssetMeta("EUCPI", "Inflation zone euro (IPC)", A.CPI, C.EUR, "inflation/EUCPI.csv"),
    AssetMeta("EURBGN", "EUR/USD (USD pour 1 EUR)", A.FX, C.USD, "currency/Euro.csv"),
]

BY_CODE: dict[str, AssetMeta] = {a.code: a for a in ASSETS}

# Conventional codes used by the risk engine.
FX_CODE = "EURBGN"
CASH_CODE = {C.USD: "SBWMUD1L", C.EUR: "SBWMEU1L"}
CPI_CODE = {C.USD: "USCPI", C.EUR: "EUCPI"}

# Classes a user can actually allocate to (CPI/FX are internal-only).
INVESTABLE_CLASSES = [A.EQUITY, A.BOND, A.HIGH_YIELD, A.HEDGE_FUND, A.CTA, A.CASH]
