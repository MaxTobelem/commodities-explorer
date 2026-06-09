"""GDELT-based event provider (https://www.gdeltproject.org/).

Heuristic, non-LLM linkage: GDELT conflict signal in a commodity's *top
producing countries* (already in our DB) → a candidate supply-impacting event
for that commodity. Results are tagged needs_review for admin validation.

INTEGRATION NOTE: the exact GDELT query/threshold should be tuned against live
data; the linkage logic below is the durable, tested part.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import requests
from django.conf import settings

from commodities.models import CommodityProduction, Event, EventImpact

from .base import EnrichmentProvider, EnrichmentResult, ImpactRecord

if TYPE_CHECKING:
    from commodities.models import Commodity, Country

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


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

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        result = EnrichmentResult()
        year = dt.date.today().year
        for commodity in commodities:
            top = (
                CommodityProduction.objects.filter(commodity=commodity)
                .order_by("-production_t")
                .select_related("country")[: self.max_countries]
            )
            for production in top:
                signal = self._conflict_signal(production.country)
                if signal is None:
                    continue
                result.impacts.append(
                    ImpactRecord(
                        commodity=commodity,
                        event_title=f"Tensions en {production.country.name} ({year})",
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

    def _conflict_signal(self, country: Country) -> dict[str, Any] | None:
        """Return a signal dict if conflict coverage for `country` is significant."""
        payload = self._query_gdelt(country.name)
        articles = payload.get("articles") or []
        if len(articles) < self.article_threshold:
            return None
        first = articles[0]
        return {"summary": first.get("title", ""), "url": first.get("url", "")}

    def _query_gdelt(self, country_name: str) -> dict[str, Any]:
        params = {
            "query": f'"{country_name}" (conflict OR mine OR supply OR sanctions)',
            "mode": "artlist",
            "format": "json",
            "maxrecords": 50,
            "timespan": "1m",
        }
        response = requests.get(GDELT_DOC_API, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
