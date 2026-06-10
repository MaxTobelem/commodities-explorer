"""Our World in Data — production by country (agriculture from FAOSTAT, energy
from the Energy Institute), as clean per-commodity CSVs with ISO3 codes. Keyless.

Agriculture is in tonnes, energy in TWh (the unit travels on the record). Keyed
by Commodity.price_symbol (the World Bank label) → (OWID chart slug, column, unit).
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import requests
from django.conf import settings

from .base import EnrichmentProvider, EnrichmentResult, ProductionRecord

if TYPE_CHECKING:
    from commodities.models import Commodity

OWID_URL = "https://ourworldindata.org/grapher/{slug}.csv?csvType=full&useColumnShortNames=true"
USER_AGENT = "Mozilla/5.0 (commodities-explorer research dashboard)"

DEFAULT_OWID = {
    # Énergie (TWh)
    "Crude oil, Brent": ("oil-production-by-country", "oil_production__twh", "TWh"),
    "Natural gas, Europe": ("gas-production-by-country", "gas_production__twh", "TWh"),
    "Natural gas, US": ("gas-production-by-country", "gas_production__twh", "TWh"),
    "Liquefied natural gas, Japan": ("gas-production-by-country", "gas_production__twh", "TWh"),
    "Coal, Australian": ("coal-production-by-country", "coal_production__twh", "TWh"),
    # Agricole (tonnes)
    "Wheat, US HRW": ("wheat-production", "wheat__00000015__production__005510__tonnes", "t"),
    "Rice, Thai 5%": ("rice-production", "rice__00000027__production__005510__tonnes", "t"),
    "Maize": ("maize-production", "maize__00000056__production__005510__tonnes", "t"),
    "Barley": ("barley-production", "barley__00000044__production__005510__tonnes", "t"),
    "Sugar, world": ("sugar-cane-production", "sugar_cane__00000156__production__005510__tonnes", "t"),
    "Coffee, Arabica": (
        "coffee-bean-production",
        "coffee__green__00000656__production__005510__tonnes",
        "t",
    ),
    "Cocoa": ("cocoa-bean-production", "cocoa_beans__00000661__production__005510__tonnes", "t"),
    "Soybeans": ("soybean-production", "soybeans__00000236__production__005510__tonnes", "t"),
    "Banana, US": ("banana-production", "bananas__00000486__production__005510__tonnes", "t"),
    "Palm oil": ("palm-oil-production", "palm_oil__00000257__production__005510__tonnes", "t"),
    "Tobacco, US import u.v.": (
        "tobacco-production",
        "tobacco__00000826__production__005510__tonnes",
        "t",
    ),
}


class OwidProvider(EnrichmentProvider):
    key = "owid"

    @property
    def enabled(self) -> bool:
        return getattr(settings, "OWID_ENABLED", True)

    @property
    def timeout(self) -> int:
        return getattr(settings, "OWID_TIMEOUT", 30)

    @property
    def mapping(self) -> dict[str, tuple[str, str, str]]:
        return {**DEFAULT_OWID, **getattr(settings, "OWID_PRODUCTION", {})}

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        if not self.enabled:
            return EnrichmentResult()
        result = EnrichmentResult()
        mapping = self.mapping
        cache: dict[str, list[tuple[str, str, int, Decimal]]] = {}
        for commodity in commodities:
            cfg = mapping.get(commodity.price_symbol)
            if not cfg:
                continue
            owid_slug, column, unit = cfg
            if owid_slug not in cache:
                cache[owid_slug] = self._latest_by_country(owid_slug, column)
            for iso3, name, year, value in cache[owid_slug]:
                result.production.append(
                    ProductionRecord(commodity, iso3, name, year, value, "owid", unit=unit)
                )
        return result

    def _latest_by_country(self, slug: str, column: str) -> list[tuple[str, str, int, Decimal]]:
        response = requests.get(
            OWID_URL.format(slug=slug), headers={"User-Agent": USER_AGENT}, timeout=self.timeout
        )
        response.raise_for_status()
        latest: dict[str, tuple[str, int, Decimal]] = {}  # iso3 -> (name, year, value)
        for row in csv.DictReader(io.StringIO(response.text)):
            code = (row.get("code") or "").strip()
            if len(code) != 3:  # skip aggregates / regions (e.g. OWID_WRL, World)
                continue
            try:
                year = int(row["year"])
                value = Decimal(str(row[column]).strip())
            except (KeyError, ValueError, InvalidOperation):
                continue
            if value <= 0:
                continue
            if code not in latest or year > latest[code][1]:
                latest[code] = ((row.get("entity") or "").strip(), year, value.quantize(Decimal("0.01")))
        return [(code, name, year, value) for code, (name, year, value) in latest.items()]
