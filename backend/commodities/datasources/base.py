"""Contracts for pluggable data sources.

A `PriceProvider` fetches daily prices (USD + EUR) for a batch of commodities.
An `EnrichmentProvider` returns slow-changing, authoritative data (reserves,
production, sector usages, product compositions, impacting events). Swapping or
adding a source is a matter of implementing one of these and registering it.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from commodities.models import Commodity


@dataclass(frozen=True)
class PriceData:
    """A single price point for one commodity, in the commodity's native unit."""

    commodity: Commodity
    date: dt.date
    price_usd: Decimal
    price_eur: Decimal | None
    source: str


class PriceProvider(ABC):
    """Fetches latest prices for a batch of commodities in one shot."""

    #: registry key, e.g. "commodities_api"
    key: str = ""

    @abstractmethod
    def fetch_latest(self, commodities: list[Commodity]) -> list[PriceData]:
        """Return one PriceData per commodity that could be priced.

        Implementations should batch network calls and skip (rather than raise
        for) individual commodities that the upstream API does not cover.
        """
        raise NotImplementedError


# --- Enrichment (slow-changing, authoritative data) -------------------------
#
# Records reference the Commodity instance directly; countries/sectors/products/
# events are referenced by natural keys (iso3 / name / title) and resolved or
# created by the import service.


@dataclass(frozen=True)
class ReserveRecord:
    commodity: Commodity
    country_iso3: str
    country_name: str
    year: int
    reserves_t: Decimal
    source: str


@dataclass(frozen=True)
class ProductionRecord:
    commodity: Commodity
    country_iso3: str
    country_name: str
    year: int
    production_t: Decimal
    source: str
    unit: str = "t"


@dataclass(frozen=True)
class UsageRecord:
    commodity: Commodity
    sector_name: str
    share_percent: Decimal | None
    description: str
    source: str
    nace_code: str = ""


@dataclass(frozen=True)
class CompositionRecord:
    commodity: Commodity
    product_name: str
    role: str
    source: str


@dataclass(frozen=True)
class ImpactRecord:
    commodity: Commodity
    event_title: str
    event_type: str
    start_date: dt.date | None
    description: str
    source_url: str
    direction: str
    magnitude: Decimal | None
    source: str


@dataclass
class EnrichmentResult:
    reserves: list[ReserveRecord] = field(default_factory=list)
    production: list[ProductionRecord] = field(default_factory=list)
    usages: list[UsageRecord] = field(default_factory=list)
    compositions: list[CompositionRecord] = field(default_factory=list)
    impacts: list[ImpactRecord] = field(default_factory=list)

    def extend(self, other: EnrichmentResult) -> None:
        self.reserves += other.reserves
        self.production += other.production
        self.usages += other.usages
        self.compositions += other.compositions
        self.impacts += other.impacts


class EnrichmentProvider(ABC):
    """Returns slow-changing data for a batch of commodities (monthly cadence)."""

    key: str = ""

    @abstractmethod
    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        raise NotImplementedError

