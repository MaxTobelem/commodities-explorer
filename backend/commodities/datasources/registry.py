"""Registries mapping provider keys to instances. Lets us add/swap data sources
without touching callers (commands, services, admin)."""

from __future__ import annotations

from .base import EnrichmentProvider, PriceProvider
from .commodities_api import CommoditiesApiProvider
from .gdelt import GdeltProvider
from .rmis import RmisProvider
from .usgs import UsgsProvider

# Price providers: keyed by Commodity.price_provider.
_PRICE_PROVIDERS: dict[str, PriceProvider] = {
    CommoditiesApiProvider.key: CommoditiesApiProvider(),
}

# Enrichment providers: all run during the monthly enrichment pass.
_ENRICHMENT_PROVIDERS: list[EnrichmentProvider] = [
    UsgsProvider(),
    RmisProvider(),
    GdeltProvider(),
]


def get_price_provider(key: str) -> PriceProvider | None:
    return _PRICE_PROVIDERS.get(key)


def register_price_provider(provider: PriceProvider) -> None:
    _PRICE_PROVIDERS[provider.key] = provider


def get_enrichment_providers() -> list[EnrichmentProvider]:
    return list(_ENRICHMENT_PROVIDERS)


def register_enrichment_provider(provider: EnrichmentProvider) -> None:
    _ENRICHMENT_PROVIDERS.append(provider)
