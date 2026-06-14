"""Registries mapping provider keys to instances. Lets us add/swap data sources
without touching callers (commands, services, admin)."""

from __future__ import annotations

from .base import EnrichmentProvider, PriceProvider
from .commodities_api import CommoditiesApiProvider
from .gnews import GoogleNewsProvider
from .mining import MiningNewsProvider
from .owid import OwidProvider
from .presse import PresseProvider
from .rmis import RmisProvider
from .usgs import UsgsProvider
from .usgs_price import UsgsPriceProvider
from .worldbank import WorldBankProvider

# Price providers: keyed by Commodity.price_provider.
_PRICE_PROVIDERS: dict[str, PriceProvider] = {
    CommoditiesApiProvider.key: CommoditiesApiProvider(),
    WorldBankProvider.key: WorldBankProvider(),
    UsgsPriceProvider.key: UsgsPriceProvider(),
}

# Enrichment providers: all run during the monthly enrichment pass. The news
# providers (presse, mining, gnews) are also driven by refresh_events on a daily
# cadence: presse (FR, energy/agri) + mining (EN, metals) are primary, gnews fills
# whatever neither covers.
_ENRICHMENT_PROVIDERS: list[EnrichmentProvider] = [
    UsgsProvider(),
    OwidProvider(),
    RmisProvider(),
    PresseProvider(),
    MiningNewsProvider(),
    GoogleNewsProvider(),
]


def get_price_provider(key: str) -> PriceProvider | None:
    return _PRICE_PROVIDERS.get(key)


def register_price_provider(provider: PriceProvider) -> None:
    _PRICE_PROVIDERS[provider.key] = provider


def get_enrichment_providers() -> list[EnrichmentProvider]:
    return list(_ENRICHMENT_PROVIDERS)


def register_enrichment_provider(provider: EnrichmentProvider) -> None:
    _ENRICHMENT_PROVIDERS.append(provider)
