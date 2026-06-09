"""GDELT-based event provider (https://www.gdeltproject.org/).

Heuristic, non-LLM linkage: a conflict/instability signal in a commodity's *top
producing countries* (already in our DB) → a candidate supply-impacting event
for that commodity, tagged needs_review for admin validation.

The public DOC 2.0 API is rate-limited (≈1 request / 5 s) and returns a plain
text notice (not JSON) on 429, so we pace requests, back off on 429, isolate
per-country failures, and query with the English country name (GDELT indexes
mostly English-language news).
"""

from __future__ import annotations

import datetime as dt
import time
from typing import TYPE_CHECKING, Any

import requests
from django.conf import settings

from commodities.models import CommodityProduction, Event, EventImpact

from .base import EnrichmentProvider, EnrichmentResult, ImpactRecord

if TYPE_CHECKING:
    from commodities.models import Commodity, Country

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "commodities-explorer/1.0 (research dashboard)"

# Minimal ISO3 → English name map for building GDELT queries; falls back to the
# stored (French) name. Extended automatically once USGS imports English names.
COUNTRY_EN = {
    "CHN": "China", "AUS": "Australia", "COD": "Democratic Republic of the Congo",
    "RUS": "Russia", "GIN": "Guinea", "IDN": "Indonesia", "USA": "United States",
    "CAN": "Canada", "ZAF": "South Africa", "BRA": "Brazil", "IND": "India",
    "PER": "Peru", "CHL": "Chile", "PHL": "Philippines", "KAZ": "Kazakhstan",
    "MDG": "Madagascar", "ZMB": "Zambia", "MEX": "Mexico", "GHA": "Ghana",
}


class GdeltProvider(EnrichmentProvider):
    key = "gdelt"

    @property
    def max_countries(self) -> int:
        return getattr(settings, "GDELT_MAX_COUNTRIES", 2)

    @property
    def article_threshold(self) -> int:
        return getattr(settings, "GDELT_ARTICLE_THRESHOLD", 10)

    @property
    def timeout(self) -> int:
        return getattr(settings, "GDELT_TIMEOUT", 20)

    @property
    def request_delay(self) -> float:
        # Seconds between requests to respect the public rate limit.
        return getattr(settings, "GDELT_REQUEST_DELAY", 6.0)

    def __init__(self) -> None:
        self._last_request_at = 0.0

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        result = EnrichmentResult()
        year = dt.date.today().year
        # Each producing country is queried once, then reused across commodities.
        signal_cache: dict[str, dict[str, Any] | None] = {}
        for commodity in commodities:
            top = (
                CommodityProduction.objects.filter(commodity=commodity)
                .order_by("-production_t")
                .select_related("country")[: self.max_countries]
            )
            for production in top:
                country = production.country
                if country.iso3 not in signal_cache:
                    signal_cache[country.iso3] = self._safe_signal(country)
                signal = signal_cache[country.iso3]
                if signal is None:
                    continue
                result.impacts.append(
                    ImpactRecord(
                        commodity=commodity,
                        event_title=f"Tensions en {country.name} ({year})",
                        event_type=Event.Type.WAR,
                        start_date=dt.date(year, 1, 1),
                        description=signal.get("summary", ""),
                        source_url=signal.get("url", ""),
                        direction=EventImpact.Direction.UP,
                        magnitude=None,
                        source=self.key,
                    )
                )
        return result

    # -- internals -----------------------------------------------------------

    def _safe_signal(self, country: Country) -> dict[str, Any] | None:
        """Per-country isolation: a failure for one country never aborts the rest."""
        try:
            return self._conflict_signal(country)
        except requests.RequestException:
            return None

    def _conflict_signal(self, country: Country) -> dict[str, Any] | None:
        name_en = COUNTRY_EN.get(country.iso3, country.name)
        payload = self._query_gdelt(name_en)
        articles = payload.get("articles") or []
        if len(articles) < self.article_threshold:
            return None
        first = articles[0]
        return {"summary": first.get("title", ""), "url": first.get("url", "")}

    def _query_gdelt(self, country_name: str) -> dict[str, Any]:
        params = {
            "query": f'"{country_name}" (conflict OR mining OR mine OR supply OR sanctions) sourcelang:english',
            "mode": "artlist",
            "format": "json",
            "maxrecords": 75,
            "timespan": "1month",
        }
        headers = {"User-Agent": USER_AGENT}
        for attempt in range(2):
            self._respect_rate_limit()
            response = requests.get(GDELT_DOC_API, params=params, headers=headers, timeout=self.timeout)
            if response.status_code == 429:
                time.sleep(self.request_delay)  # back off, then retry once
                continue
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {}  # GDELT occasionally returns an empty/non-JSON body
        return {}  # still rate-limited after a retry — treat as "no signal"

    def _respect_rate_limit(self) -> None:
        if self.request_delay <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_at = time.monotonic()
