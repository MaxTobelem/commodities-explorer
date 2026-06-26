"""Performance & risk metrics — pure NumPy, no Django.

Keeping this module DB-free means every formula can be pinned by a closed-form unit
test on a synthetic series. All returns are **fractions** (0.08 = 8 %); the API/UI
layer formats them. Conventions (a clean rewrite of the iMGP simulator, with its
known issues fixed):

* **CAGR** is the headline return — geometric ``(end/start)^(12/m) - 1`` over ``m``
  monthly steps (the old code mixed this with a mean of rolling 12-month returns).
* **Volatility** is ``std(monthly, ddof=1) * sqrt(12)`` (annualised from monthly).
* **Sharpe** = ``(CAGR - rf) / vol`` with ``rf`` = the cash index CAGR.
* **VaR** is **historical** (empirical quantile), reported as a **positive loss** at
  the confidence level; monthly is primary, annual is the monthly figure scaled by
  ``sqrt(12)`` (no overlapping windows, unlike the old code).
* Benchmark-relative metrics use the **geometric active return** ``(1+rp)/(1+rb)-1``.
"""

from __future__ import annotations

import datetime as dt
import math

import numpy as np

PERIODS_PER_YEAR = 12
VAR_CONFIDENCES = (0.90, 0.95, 0.98, 0.99)


def monthly_returns(equity) -> np.ndarray:
    """Period-over-period returns of an equity curve (length ``n`` → ``n-1``)."""
    e = np.asarray(equity, dtype=float)
    if e.size < 2:
        return np.array([])
    return e[1:] / e[:-1] - 1.0


def cagr(equity, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Compound annual growth rate from an equity curve."""
    e = np.asarray(equity, dtype=float)
    m = e.size - 1
    if m <= 0 or e[0] <= 0 or e[-1] <= 0:
        return 0.0
    return float((e[-1] / e[0]) ** (periods_per_year / m) - 1.0)


def annual_return_arith(returns, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Arithmetic annualised return = mean(monthly) × periods/year."""
    r = np.asarray(returns, dtype=float)
    return float(r.mean() * periods_per_year) if r.size else 0.0


def annual_volatility(returns, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Annualised volatility = sample std(monthly) × sqrt(periods/year)."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    return float(r.std(ddof=1) * math.sqrt(periods_per_year))


def sharpe_ratio(equity, rf_cagr: float, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """(CAGR − risk-free CAGR) / annualised volatility."""
    vol = annual_volatility(monthly_returns(equity), periods_per_year)
    if vol == 0:
        return 0.0
    return (cagr(equity, periods_per_year) - rf_cagr) / vol


def historical_var(returns, confidence: float) -> float:
    """Empirical Value-at-Risk: the loss (positive) not exceeded with probability
    ``confidence`` over one period. ``VaR_95 = -quantile(returns, 5%)``."""
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    return float(-np.percentile(r, (1.0 - confidence) * 100.0))


def var_table(returns, confidences=VAR_CONFIDENCES) -> dict[str, dict[str, float]]:
    """Monthly (historical) and annual (sqrt-scaled) VaR at each confidence level."""
    out: dict[str, dict[str, float]] = {}
    for c in confidences:
        monthly = historical_var(returns, c)
        out[str(int(round(c * 100)))] = {
            "monthly": monthly,
            "annual": monthly * math.sqrt(PERIODS_PER_YEAR),
        }
    return out


def drawdown_series(equity) -> np.ndarray:
    """Drawdown at each point: ``value / running_peak - 1`` (≤ 0)."""
    e = np.asarray(equity, dtype=float)
    if e.size == 0:
        return np.array([])
    peak = np.maximum.accumulate(e)
    return e / peak - 1.0


def max_drawdown(equity) -> float:
    """Worst peak-to-trough decline (a negative fraction)."""
    dd = drawdown_series(equity)
    return float(dd.min()) if dd.size else 0.0


def calendar_year_returns(dates: list[dt.date], equity) -> list[tuple[int, float]]:
    """Per calendar-year return, year-end over previous year-end (the first reported
    year runs from inception to its year-end)."""
    e = np.asarray(equity, dtype=float)
    if e.size == 0:
        return []
    year_last: dict[int, int] = {}
    for i, d in enumerate(dates):
        year_last[d.year] = i  # dates ascending → last index per year wins
    out: list[tuple[int, float]] = []
    prev = e[0]
    for year in sorted(year_last):
        idx = year_last[year]
        if idx == 0:  # only the inception point lands in this year → it is the base
            continue
        out.append((year, float(e[idx] / prev - 1.0)))
        prev = e[idx]
    return out


# --- Benchmark-relative -----------------------------------------------------


def _active_returns(rp, rb) -> np.ndarray:
    rp = np.asarray(rp, dtype=float)
    rb = np.asarray(rb, dtype=float)
    return (1.0 + rp) / (1.0 + rb) - 1.0


def tracking_error(rp, rb, periods_per_year: int = PERIODS_PER_YEAR) -> float:
    """Annualised std of the geometric active return vs the benchmark."""
    active = _active_returns(rp, rb)
    if active.size < 2:
        return 0.0
    return float(active.std(ddof=1) * math.sqrt(periods_per_year))


def capture_ratio(rp, rb, *, upside: bool) -> float:
    """Up/down capture: portfolio cumulative return over the months where the
    benchmark was up (resp. down), divided by the benchmark's, ×100."""
    rp = np.asarray(rp, dtype=float)
    rb = np.asarray(rb, dtype=float)
    mask = rb > 0 if upside else rb < 0
    if not mask.any():
        return 0.0
    cum_p = float(np.prod(1.0 + rp[mask]) - 1.0)
    cum_b = float(np.prod(1.0 + rb[mask]) - 1.0)
    if cum_b == 0:
        return 0.0
    return cum_p / cum_b * 100.0


def best_worst_relative(rp, rb, dates: list[dt.date]) -> dict[str, dict]:
    """Best & worst single month of geometric active return (value + its date).
    ``dates`` aligns with the equity curve (length ``n``); returns are ``n-1`` long
    and correspond to ``dates[1:]``."""
    active = _active_returns(rp, rb)
    if active.size == 0:
        return {"best": None, "worst": None}
    rdates = dates[1:] if len(dates) == active.size + 1 else dates[: active.size]
    bi = int(np.argmax(active))
    wi = int(np.argmin(active))
    return {
        "best": {"value": float(active[bi]), "date": rdates[bi]},
        "worst": {"value": float(active[wi]), "date": rdates[wi]},
    }
