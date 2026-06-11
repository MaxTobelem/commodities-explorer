"""Commodities-API price provider (https://www.commodities-api.com/).

Single provider covering aluminium (ALU), cobalt (LCO), gold (XAU), silver
(XAG), copper (XCU), nickel (NI), zinc, lead, lithium... in one batched call,
returning prices in USD and EUR.

Convention: the `/latest` endpoint returns rates relative to the base currency
(USD), i.e. "how many units of the symbol per 1 USD"; the price per unit is
therefore ``1 / rate``. EUR is requested as an extra symbol so we can convert
``price_eur = price_usd * (EUR per USD)`` from the same call (single source).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

import requests
from django.conf import settings

from .base import PriceData, PriceProvider

if TYPE_CHECKING:
    from commodities.models import Commodity

_QUANT = Decimal("0.0001")

# Commodities-API quotes each symbol in its own native unit (metals per troy ounce;
# ags per lb / bushel / cwt / tonne, sometimes in US cents), which rarely matches our
# canonical `price_unit`. The API's `unit` field gives the dimension but not the
# precision — it labels base metals "per ounce" though they are troy, and never
# distinguishes cents from dollars — so we pin a factor per symbol, each validated
# against the World Bank series. The factor assumes the catalog's canonical price_unit
# and is applied to `1 / rate` BEFORE rounding (so tiny rates like iron keep precision).
_TROY_OZ_PER_TONNE = Decimal("32150.7466")  # 1 t / 31.1034768 g
_LB_PER_KG = Decimal("2.2046226218")
_UNIT_FACTOR: dict[str, Decimal] = {
    # Base / battery metals: API per troy ounce → canonical USD/t.
    "ALU": _TROY_OZ_PER_TONNE,
    "XCU": _TROY_OZ_PER_TONNE,
    "NI": _TROY_OZ_PER_TONNE,
    "LEAD": _TROY_OZ_PER_TONNE,
    "LME-ZNC": _TROY_OZ_PER_TONNE,
    "TIN": _TROY_OZ_PER_TONNE,
    "LCO": _TROY_OZ_PER_TONNE,
    "IRON": _TROY_OZ_PER_TONNE,  # canonical USD/dmtu ≈ USD/t
    # Agriculturals.
    "COCOA": Decimal("0.001"),              # USD/tonne → USD/kg
    "SUGAR": _LB_PER_KG,                    # USD/lb → USD/kg
    "COTTON": _LB_PER_KG,                   # USD/lb → USD/kg
    "COFFEE": _LB_PER_KG / 100,             # US cents/lb → USD/kg
    "CORN": _LB_PER_KG * 1000 / 56 / 100,   # US cents/bushel (56 lb) → USD/t
    "SOYBEAN": _LB_PER_KG * 1000 / 60,      # USD/bushel (60 lb) → USD/t
    "RICE": _LB_PER_KG * 1000 / 100,        # USD/cwt (100 lb) → USD/t
    # Already canonical (factor 1, omitted): XAU/XAG/XPT (USD/ozt), WHEAT/COAL (USD/t),
    # NG (USD/mmbtu), BRENTOIL (USD/bbl).
}


class CommoditiesApiProvider(PriceProvider):
    key = "commodities_api"

    # Settings are read lazily so env changes (and test overrides) take effect.

    @property
    def base_url(self) -> str:
        return getattr(
            settings, "COMMODITIES_API_BASE_URL", "https://api.commodities-api.com/api"
        ).rstrip("/")

    @property
    def api_key(self) -> str:
        return getattr(settings, "COMMODITIES_API_KEY", "")

    @property
    def rate_is_per_usd(self) -> bool:
        # Guards against the upstream rate convention being inverted.
        return getattr(settings, "COMMODITIES_API_RATE_IS_PER_USD", True)

    @property
    def timeout(self) -> int:
        return getattr(settings, "COMMODITIES_API_TIMEOUT", 20)

    @property
    def max_symbols(self) -> int:
        # Plan-dependent cap on symbols per request (PRO=10, PRO PLUS=15…).
        return getattr(settings, "COMMODITIES_API_MAX_SYMBOLS", 10)

    # -- public --------------------------------------------------------------

    def fetch_latest(self, commodities: list[Commodity]) -> list[PriceData]:
        symbol_to_commodity: dict[str, Commodity] = {}
        for commodity in commodities:
            if commodity.api_symbol:
                symbol_to_commodity.setdefault(commodity.api_symbol.upper(), commodity)
        if not symbol_to_commodity:
            return []

        # The upstream caps symbols per request (plan-dependent); chunk and merge.
        # One slot is reserved for EUR (appended by _request) for the conversion.
        symbols = sorted(symbol_to_commodity)
        per_request = max(1, self.max_symbols - 1)
        rates: dict[str, Any] = {}
        quote_date: dt.date | None = None
        for start in range(0, len(symbols), per_request):
            payload = self._request(symbols[start : start + per_request])
            rates.update(self._extract_rates(payload))
            if quote_date is None:
                quote_date = self._extract_date(payload)
        if quote_date is None:
            quote_date = dt.date.today()
        eur_per_usd = self._to_decimal(rates.get("EUR"))

        results: list[PriceData] = []
        for symbol, commodity in symbol_to_commodity.items():
            price_usd = self._price_from_rate(rates.get(symbol))
            if price_usd is None:
                continue  # symbol not covered by the upstream API — skip, don't fail
            price_usd = (price_usd * self._unit_factor(symbol)).quantize(_QUANT)
            price_eur = (
                (price_usd * eur_per_usd).quantize(_QUANT) if eur_per_usd is not None else None
            )
            results.append(
                PriceData(
                    commodity=commodity,
                    date=quote_date,
                    price_usd=price_usd,
                    price_eur=price_eur,
                    source=self.key,
                )
            )
        return results

    def fetch_timeseries(
        self, commodities: list[Commodity], start: dt.date, end: dt.date
    ) -> list[PriceData]:
        """Historical daily prices over [start, end], for backfilling charts."""
        symbol_to_commodity: dict[str, Commodity] = {}
        for commodity in commodities:
            if commodity.api_symbol:
                symbol_to_commodity.setdefault(commodity.api_symbol.upper(), commodity)
        if not symbol_to_commodity:
            return []

        # Chunk under the plan's per-request symbol cap (EUR reserves one slot),
        # merging each chunk's per-date rate maps.
        symbols = sorted(symbol_to_commodity)
        per_request = max(1, self.max_symbols - 1)
        rates_by_date: dict[str, Any] = {}
        for offset in range(0, len(symbols), per_request):
            payload = self._request_timeseries(symbols[offset : offset + per_request], start, end)
            for date_str, day_rates in self._extract_rates(payload).items():
                if isinstance(day_rates, dict):
                    rates_by_date.setdefault(date_str, {}).update(day_rates)

        results: list[PriceData] = []
        for date_str, day_rates in rates_by_date.items():
            if not isinstance(day_rates, dict):
                continue
            try:
                quote_date = dt.date.fromisoformat(str(date_str)[:10])
            except ValueError:
                continue
            eur_per_usd = self._to_decimal(day_rates.get("EUR"))
            for symbol, commodity in symbol_to_commodity.items():
                price_usd = self._price_from_rate(day_rates.get(symbol))
                if price_usd is None:
                    continue
                price_usd = (price_usd * self._unit_factor(symbol)).quantize(_QUANT)
                price_eur = (
                    (price_usd * eur_per_usd).quantize(_QUANT) if eur_per_usd is not None else None
                )
                results.append(
                    PriceData(
                        commodity=commodity,
                        date=quote_date,
                        price_usd=price_usd,
                        price_eur=price_eur,
                        source=self.key,
                    )
                )
        return results

    # -- internals -----------------------------------------------------------

    def _request(self, symbols: list[str]) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "COMMODITIES_API_KEY manquant — configurez la clé dans l'environnement."
            )
        params = {
            "access_key": self.api_key,
            "base": "USD",
            "symbols": ",".join([*symbols, "EUR"]),
        }
        response = requests.get(f"{self.base_url}/latest", params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") is False:
            raise RuntimeError(f"Commodities-API erreur: {payload.get('error')}")
        return payload

    def _request_timeseries(
        self, symbols: list[str], start: dt.date, end: dt.date
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError(
                "COMMODITIES_API_KEY manquant — configurez la clé dans l'environnement."
            )
        params = {
            "access_key": self.api_key,
            "base": "USD",
            "symbols": ",".join([*symbols, "EUR"]),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        response = requests.get(
            f"{self.base_url}/timeseries", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") is False:
            raise RuntimeError(f"Commodities-API erreur: {payload.get('error')}")
        return payload

    @staticmethod
    def _extract_rates(payload: dict[str, Any]) -> dict[str, Any]:
        if "rates" in payload:
            return payload["rates"] or {}
        data = payload.get("data") or {}
        return data.get("rates") or {}

    @staticmethod
    def _extract_date(payload: dict[str, Any]) -> dt.date:
        raw = payload.get("date") or (payload.get("data") or {}).get("date")
        if isinstance(raw, str):
            try:
                return dt.date.fromisoformat(raw[:10])
            except ValueError:
                pass
        return dt.date.today()

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
        return dec if dec != 0 else None

    def _price_from_rate(self, rate: Any) -> Decimal | None:
        """USD per the symbol's *native* unit (unquantized — caller scales then rounds)."""
        dec = self._to_decimal(rate)
        if dec is None:
            return None
        return (Decimal(1) / dec) if self.rate_is_per_usd else dec

    @staticmethod
    def _unit_factor(symbol: str) -> Decimal:
        """Factor converting the symbol's native API unit to its canonical price_unit."""
        return _UNIT_FACTOR.get(symbol.upper(), Decimal(1))
