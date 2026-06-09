"""EU JRC RMIS provider — sector usages, applications and product compositions.

Source: Raw Materials Information System (European Commission, reusable with
citation). The Supply Chain Viewer maps materials → 152 product applications →
21 NACE-2 sectors; the MSA dataset gives product compositions for typical
products.

INTEGRATION NOTE: the JRC Data Catalogue (collection id-00192) ships these as
downloadable datasets rather than a turnkey per-material API. Wiring the live
download + parsing (configured via ``RMIS_DATASET_URLS``) is an integration step;
until then this provider no-ops so the pipeline keeps running.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings

from .base import EnrichmentProvider, EnrichmentResult

if TYPE_CHECKING:
    from commodities.models import Commodity


class RmisProvider(EnrichmentProvider):
    key = "rmis"

    @property
    def dataset_urls(self) -> dict[str, str]:
        return getattr(settings, "RMIS_DATASET_URLS", {})

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        # No-op until the JRC datasets are wired (see module docstring).
        return EnrichmentResult()
