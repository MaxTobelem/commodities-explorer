"""USGS annual price for commodities not covered by the World Bank (e.g. cobalt).

Reads the per-commodity USGS "salient statistics" CSV (annual price columns,
USD per pound) and converts to USD per tonne. Configured per commodity slug via
USGS_PRICE_CONFIG = {slug: (sciencebase_item_id, price_column)}.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import requests
from django.conf import settings

from .base import PriceData, PriceProvider
from .usgs import SCIENCEBASE_ITEM, USER_AGENT

if TYPE_CHECKING:
    from commodities.models import Commodity

_QUANT = Decimal("0.0001")
LB_PER_TONNE = Decimal("2204.62262")

# slug -> (ScienceBase item id, price column in the salient CSV, in USD/lb)
DEFAULT_USGS_PRICE = {
    "cobalt": ("6797fb00d34ea8c18376e159", "Price_Spot_dlb"),  # US spot cathode, $/lb
}


class UsgsPriceProvider(PriceProvider):
    key = "usgs_price"

    @property
    def config(self) -> dict[str, tuple[str, str]]:
        return {**DEFAULT_USGS_PRICE, **getattr(settings, "USGS_PRICE_CONFIG", {})}

    @property
    def timeout(self) -> int:
        return getattr(settings, "USGS_TIMEOUT", 60)

    @property
    def eur_usd(self) -> Decimal:
        return Decimal(str(getattr(settings, "EUR_USD_RATE", "0.92")))

    def fetch_latest(self, commodities: list[Commodity]) -> list[PriceData]:
        results: list[PriceData] = []
        for commodity in commodities:
            points = self._series_for(commodity)
            if points:
                year, usd = points[-1]
                results.append(self._price(commodity, dt.date(year, 7, 1), usd))
        return results

    def fetch_timeseries(
        self, commodities: list[Commodity], start: dt.date, end: dt.date
    ) -> list[PriceData]:
        results: list[PriceData] = []
        for commodity in commodities:
            for year, usd in self._series_for(commodity):
                date = dt.date(year, 7, 1)
                if start <= date <= end:
                    results.append(self._price(commodity, date, usd))
        return results

    # -- internals -----------------------------------------------------------

    def _series_for(self, commodity: Commodity) -> list[tuple[int, Decimal]]:
        cfg = self.config.get(commodity.slug)
        if not cfg:
            return []
        item_id, column = cfg
        csv_text = self._download_salient(item_id)
        if not csv_text:
            return []
        points: list[tuple[int, Decimal]] = []
        for row in csv.DictReader(io.StringIO(csv_text)):
            try:
                year = int(row["Year"])
                per_lb = Decimal(str(row[column]).strip())
            except (KeyError, ValueError, InvalidOperation):
                continue
            points.append((year, (per_lb * LB_PER_TONNE).quantize(_QUANT)))  # $/lb → $/t
        return sorted(points)

    def _download_salient(self, item_id: str) -> str | None:
        headers = {"User-Agent": USER_AGENT}
        item = requests.get(
            SCIENCEBASE_ITEM.format(item_id=item_id), headers=headers, timeout=self.timeout
        )
        item.raise_for_status()
        files = item.json().get("files", []) or []
        url = next(
            (
                f["downloadUri"]
                for f in files
                if "salient" in str(f.get("name", "")).lower()
                and str(f.get("name", "")).lower().endswith(".csv")
            ),
            None,
        )
        if not url:
            return None
        response = requests.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.content.decode("utf-8-sig")

    def _price(self, commodity: Commodity, date: dt.date, usd: Decimal) -> PriceData:
        return PriceData(
            commodity=commodity,
            date=date,
            price_usd=usd,
            price_eur=(usd * self.eur_usd).quantize(_QUANT),
            source=self.key,
        )
