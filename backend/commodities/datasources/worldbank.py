"""World Bank "Pink Sheet" monthly commodity prices (free, no key, CC BY 4.0).

One Excel download holds monthly USD prices since 1960 for aluminium, copper,
gold, silver, nickel, zinc, lead… Commodity.price_symbol must hold the World Bank
column label (e.g. "Aluminum", "Gold"). EUR is an approximate conversion via the
configurable EUR_USD_RATE (the Pink Sheet is USD-only).
"""

from __future__ import annotations

import datetime as dt
import io
import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import openpyxl
import requests
from django.conf import settings

from .base import PriceData, PriceProvider

if TYPE_CHECKING:
    from commodities.models import Commodity

DEFAULT_URL = (
    "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/"
    "related/CMO-Historical-Data-Monthly.xlsx"
)
_QUANT = Decimal("0.0001")
_MONTH_RE = re.compile(r"^(\d{4})M(\d{2})$")


class WorldBankProvider(PriceProvider):
    key = "worldbank"

    @property
    def url(self) -> str:
        return getattr(settings, "WORLD_BANK_XLSX_URL", DEFAULT_URL)

    @property
    def timeout(self) -> int:
        return getattr(settings, "WORLD_BANK_TIMEOUT", 60)

    @property
    def eur_usd(self) -> Decimal:
        return Decimal(str(getattr(settings, "EUR_USD_RATE", "0.92")))

    def fetch_latest(self, commodities: list[Commodity]) -> list[PriceData]:
        series = self._load_series([c.price_symbol for c in commodities if c.price_symbol])
        results: list[PriceData] = []
        for commodity in commodities:
            points = series.get(commodity.price_symbol)
            if points:
                date, usd = points[-1]
                results.append(self._price(commodity, date, usd))
        return results

    def fetch_timeseries(
        self, commodities: list[Commodity], start: dt.date, end: dt.date
    ) -> list[PriceData]:
        series = self._load_series([c.price_symbol for c in commodities if c.price_symbol])
        results: list[PriceData] = []
        for commodity in commodities:
            for date, usd in series.get(commodity.price_symbol, []):
                if start <= date <= end:
                    results.append(self._price(commodity, date, usd))
        return results

    # -- internals -----------------------------------------------------------

    def _price(self, commodity: Commodity, date: dt.date, usd: Decimal) -> PriceData:
        usd_q = usd.quantize(_QUANT)
        return PriceData(
            commodity=commodity,
            date=date,
            price_usd=usd_q,
            price_eur=(usd_q * self.eur_usd).quantize(_QUANT),
            source=self.key,
        )

    def _load_series(self, wb_names: list[str]) -> dict[str, list[tuple[dt.date, Decimal]]]:
        wanted = {n for n in wb_names if n}
        if not wanted:
            return {}
        response = requests.get(self.url, timeout=self.timeout)
        response.raise_for_status()
        workbook = openpyxl.load_workbook(io.BytesIO(response.content), read_only=True, data_only=True)
        sheet = workbook["Monthly Prices"]
        rows = list(sheet.iter_rows(values_only=True))
        header = rows[4]  # row 5: commodity names
        cols = {name: idx for idx, name in enumerate(header) if name in wanted}
        series: dict[str, list[tuple[dt.date, Decimal]]] = {name: [] for name in cols}
        for row in rows[6:]:
            if not row or not row[0]:
                continue
            match = _MONTH_RE.match(str(row[0]).strip())
            if not match:
                continue
            date = dt.date(int(match.group(1)), int(match.group(2)), 1)
            for name, idx in cols.items():
                value = self._to_decimal(row[idx])
                if value is not None:
                    series[name].append((date, value))
        return series

    @staticmethod
    def _to_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return dec if dec > 0 else None
