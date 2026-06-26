"""Turn stored series (commodities + imported indices) into aligned monthly price
series expressed in a single backtest currency.

An **instrument reference** is ``"asset:<code>"`` (a ``MarketAsset``) or
``"commodity:<slug>"`` (a physical ``Commodity``). Everything is resampled to
month-end and FX-converted with the time series ``EURBGN`` (USD per 1 EUR) so a EUR
and a USD backtest stay consistent across decades — no single fixed rate.
"""

from __future__ import annotations

import bisect
import datetime as dt

import numpy as np

from commodities.api.views import prefer_daily_in_overlap
from commodities.models import Commodity

from .catalog import FX_CODE
from .models import AssetPrice, MarketAsset

USD = MarketAsset.Currency.USD
EUR = MarketAsset.Currency.EUR


class MarketError(Exception):
    """A backtest input problem (unknown instrument, empty common period…).
    Surfaced as HTTP 400 by the API layer."""


# --- FX ---------------------------------------------------------------------


def _fx_series() -> tuple[list[dt.date], list[float]]:
    """The EUR/USD series (USD per 1 EUR), sorted ascending."""
    rows = list(
        AssetPrice.objects.filter(asset__code=FX_CODE).order_by("date").values_list("date", "value")
    )
    return [d for d, _ in rows], [float(v) for _, v in rows]


def _carry(dates: list[dt.date], values: list[float], on: dt.date) -> float | None:
    """Last value on/before ``on`` (carry-forward); None if before the first point."""
    i = bisect.bisect_right(dates, on) - 1
    return values[i] if i >= 0 else None


def _convert(value: float, src: str, dst: str, fx: tuple[list, list], on: dt.date) -> float | None:
    """Convert ``value`` from currency ``src`` to ``dst`` using the FX rate at ``on``.
    Returns None when conversion is needed but no rate exists yet (e.g. pre-1975)."""
    if src == dst:
        return value
    rate = _carry(fx[0], fx[1], on)  # USD per 1 EUR
    if not rate:
        return None
    if src == USD and dst == EUR:
        return value / rate
    if src == EUR and dst == USD:
        return value * rate
    return value


# --- Series resolution ------------------------------------------------------


def resolve_monthly(ref: str, currency: str) -> dict[tuple[int, int], float]:
    """Month-end series for an instrument, FX-converted to ``currency``, keyed by
    ``(year, month)`` (the last observation in each month wins)."""
    kind, _, key = ref.partition(":")
    fx = _fx_series()
    out: dict[tuple[int, int], float] = {}

    if kind == "asset":
        asset = MarketAsset.objects.filter(code=key).first()
        if asset is None:
            raise MarketError(f"Indice inconnu : {key}.")
        rows = asset.prices.order_by("date").values_list("date", "value")
        for d, v in rows:
            c = _convert(float(v), asset.currency, currency, fx, d)
            if c is not None and c > 0:
                out[(d.year, d.month)] = c
        return out

    if kind == "commodity":
        commodity = Commodity.objects.filter(slug=key).first()
        if commodity is None:
            raise MarketError(f"Matière inconnue : {key}.")
        quotes = prefer_daily_in_overlap(list(commodity.prices.all()))
        quotes.sort(key=lambda q: q.date)
        for q in quotes:  # USD column is always present; FX-convert when needed
            c = _convert(float(q.price_usd), USD, currency, fx, q.date)
            if c is not None and c > 0:
                out[(q.date.year, q.date.month)] = c  # last quote of the month wins
        return out

    raise MarketError(f"Référence d'instrument inconnue : {ref}.")


# --- Alignment --------------------------------------------------------------


def _next_month(ym: tuple[int, int]) -> tuple[int, int]:
    y, m = ym
    return (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(ym: tuple[int, int]) -> dt.date:
    y, m = ym
    first_next = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
    return first_next - dt.timedelta(days=1)


def align(
    refs: list[str],
    currency: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> tuple[list[tuple[int, int]], dict[str, np.ndarray]]:
    """Resolve every ref and forward-fill onto a **common** month axis = the overlap
    of all series, clipped to ``[start, end]``. Returns the month keys and a
    ``{ref: prices}`` map of equal-length arrays."""
    maps = {r: resolve_monthly(r, currency) for r in refs}
    for r, mm in maps.items():
        if not mm:
            raise MarketError(f"Aucune donnée pour {r} en {currency}.")

    lo = max(min(mm) for mm in maps.values())
    hi = min(max(mm) for mm in maps.values())
    if start:
        lo = max(lo, (start.year, start.month))
    if end:
        hi = min(hi, (end.year, end.month))
    if lo > hi:
        raise MarketError("Période commune vide pour les actifs choisis sur cette plage.")

    months: list[tuple[int, int]] = []
    cur = lo
    while cur <= hi:
        months.append(cur)
        cur = _next_month(cur)

    series: dict[str, np.ndarray] = {}
    for r, mm in maps.items():
        keys = sorted(mm)
        vals = [mm[k] for k in keys]
        arr = np.empty(len(months), dtype=float)
        last = vals[0]
        j = 0
        for i, m in enumerate(months):
            while j < len(keys) and keys[j] <= m:
                last = vals[j]
                j += 1
            arr[i] = last
        series[r] = arr
    return months, series
