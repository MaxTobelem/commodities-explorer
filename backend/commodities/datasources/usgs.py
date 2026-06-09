"""USGS provider — world production / reserves and end-use sectors.

Source: USGS Mineral Commodity Summaries / Minerals Yearbook (public domain).

The CSV parser below is the durable, tested part. Wiring the *live* per-commodity
data-release URLs (and the country-name→ISO3 resolution) is an integration step
to validate against a real download; until configured via settings
``USGS_PRODUCTION_CSV_URLS`` (mapping price_symbol → URL), the provider no-ops.
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

# Normalised intermediate columns expected by the parser.
PRODUCTION_COLUMNS = {"iso3", "country", "year", "production_t"}


class UsgsProvider(EnrichmentProvider):
    key = "usgs"

    @property
    def production_csv_urls(self) -> dict[str, str]:
        return getattr(settings, "USGS_PRODUCTION_CSV_URLS", {})

    @property
    def timeout(self) -> int:
        return getattr(settings, "USGS_TIMEOUT", 30)

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        result = EnrichmentResult()
        urls = self.production_csv_urls
        for commodity in commodities:
            url = urls.get(commodity.price_symbol) or urls.get(commodity.slug)
            if not url:
                continue  # not wired yet — no-op
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            result.production += self.parse_production_csv(response.text, commodity)
        return result

    @staticmethod
    def parse_production_csv(text: str, commodity: Commodity) -> list[ProductionRecord]:
        """Parse a normalised world-production CSV (iso3,country,year,production_t)."""
        reader = csv.DictReader(io.StringIO(text))
        records: list[ProductionRecord] = []
        for row in reader:
            try:
                value = Decimal(str(row["production_t"]).replace(",", "").strip())
                year = int(row["year"])
            except (KeyError, ValueError, InvalidOperation):
                continue
            iso3 = (row.get("iso3") or "").strip().upper()
            name = (row.get("country") or "").strip()
            if not iso3 or not name:
                continue
            records.append(
                ProductionRecord(
                    commodity=commodity,
                    country_iso3=iso3,
                    country_name=name,
                    year=year,
                    production_t=value,
                    source="usgs",
                )
            )
        return records
