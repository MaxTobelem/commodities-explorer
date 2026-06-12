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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .base import PriceData, PriceProvider

if TYPE_CHECKING:
    from commodities.models import Commodity

DEFAULT_PAGE_URL = "https://www.worldbank.org/en/research/commodity-markets"
# Fallback direct link used only if the landing page can't be scraped — kept fresh.
DEFAULT_URL = (
    "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
    "related/CMO-Historical-Data-Monthly.xlsx"
)
_QUANT = Decimal("0.0001")
_MONTH_RE = re.compile(r"^(\d{4})M(\d{2})$")
# WB re-issues this xlsx under a new release-specific URL every month; discover the
# current one from the landing page rather than freezing on a pinned snapshot.
_XLSX_LINK_RE = re.compile(
    r"https://thedocs\.worldbank\.org/[^\"'\s]+?CMO-Historical-Data-Monthly\.xlsx"
)
_BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# The VPS network flickers (transient 'Network is unreachable' to the WB CDN);
# retry transient network/CDN failures with backoff so a blip doesn't fail the import.
_RETRY = Retry(
    total=3,
    connect=3,
    backoff_factor=1.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset(["GET"]),
)


def _session() -> requests.Session:
    """A requests session that rides over transient network blips with backoff."""
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _clean(value: object) -> str:
    """Normalise a Pink Sheet header: drop footnote '*' and collapse whitespace."""
    return " ".join(str(value).replace("*", " ").split()) if value else ""


class WorldBankProvider(PriceProvider):
    key = "worldbank"

    @property
    def url(self) -> str:
        return getattr(settings, "WORLD_BANK_XLSX_URL", DEFAULT_URL)

    @property
    def page_url(self) -> str:
        return getattr(settings, "WORLD_BANK_PAGE_URL", DEFAULT_PAGE_URL)

    @property
    def autodiscover(self) -> bool:
        # Discover the current xlsx link each run; disable to force WORLD_BANK_XLSX_URL.
        return getattr(settings, "WORLD_BANK_AUTODISCOVER", True)

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

    def _resolve_url(self) -> str:
        """Current Pink Sheet xlsx link, scraped from the WB landing page.

        WB re-issues the direct xlsx URL (release-specific doc id) every month, so a
        pinned link freezes the data. We read the landing page and extract the live
        'CMO-Historical-Data-Monthly.xlsx' link, falling back to the pinned URL
        (``settings.WORLD_BANK_XLSX_URL``) when discovery fails.
        """
        if not self.autodiscover:
            return self.url
        try:
            response = _session().get(
                self.page_url, timeout=self.timeout, headers={"User-Agent": _BROWSER_UA}
            )
            response.raise_for_status()
            match = _XLSX_LINK_RE.search(response.text)
            if match:
                return match.group(0)
        except requests.RequestException:
            pass
        return self.url

    def _load_series(self, wb_names: list[str]) -> dict[str, list[tuple[dt.date, Decimal]]]:
        wanted = {_clean(n) for n in wb_names if n}
        if not wanted:
            return {}
        response = _session().get(self._resolve_url(), timeout=self.timeout)
        response.raise_for_status()
        workbook = openpyxl.load_workbook(io.BytesIO(response.content), read_only=True, data_only=True)
        sheet = workbook["Monthly Prices"]
        rows = list(sheet.iter_rows(values_only=True))
        header = rows[4]  # row 5: commodity names
        cols = {clean: idx for idx, raw in enumerate(header) if (clean := _clean(raw)) in wanted}
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
