"""Backtest engine: simulate one or more allocations (vs an optional benchmark) over
a common monthly period, **gross and net of fees**, and attach the full risk report.

Fee model (a clean, unit-based rewrite): the portfolio holds *units* of each asset.
At entry, and at every rebalance, trading ``turnover`` notional costs
``fee_rate × turnover`` (turnover counts every leg — buys at entry, buys *and* sells
at a rebalance — so each real trade is charged once). The gross curve runs the same
simulation with a zero fee, which makes ``net ≤ gross`` hold by construction and the
two coincide exactly when ``fee_percent = 0``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from . import risk
from .catalog import CASH_CODE, CPI_CODE
from .services import MarketError, align, month_end

REBALANCE_CHOICES = ("none", "monthly", "quarterly", "annual")


@dataclass
class Allocation:
    name: str
    weights: dict[str, float]  # {instrument ref: percent}; need not sum to exactly 100

    def normalized(self) -> tuple[list[str], np.ndarray]:
        refs = [r for r, w in self.weights.items() if w]
        if not refs:
            raise MarketError(f"Allocation « {self.name} » vide.")
        w = np.array([self.weights[r] for r in refs], dtype=float)
        if (w < 0).any():
            raise MarketError("Les pondérations doivent être positives.")
        total = w.sum()
        if total <= 0:
            raise MarketError(f"Allocation « {self.name} » : somme des poids nulle.")
        return refs, w / total


@dataclass
class BacktestConfig:
    start: dt.date | None = None
    end: dt.date | None = None
    amount: float = 1000.0
    currency: str = "EUR"
    rebalance: str = "monthly"
    fee_percent: float = 0.20
    benchmark: Allocation | None = None


def _rebalance_indices(n: int, rebalance: str) -> set[int]:
    """Time indices (≥1) at which to rebalance; entry (t=0) always deploys cash."""
    if rebalance == "monthly":
        return set(range(1, n))
    if rebalance == "quarterly":
        return {t for t in range(1, n) if t % 3 == 0}
    if rebalance == "annual":
        return {t for t in range(1, n) if t % 12 == 0}
    return set()  # "none" → buy and hold


def simulate(
    prices: np.ndarray, weights: np.ndarray, amount: float, fee_rate: float, rebalance: str
) -> tuple[np.ndarray, float]:
    """Run the unit-based simulation. ``prices`` is ``T×K`` (months × assets) in the
    backtest currency. Returns the equity curve (length ``T``) and total fees paid."""
    n = prices.shape[0]
    units = np.zeros(prices.shape[1])
    cash = float(amount)
    equity = np.empty(n, dtype=float)
    fees_total = 0.0
    rebal = _rebalance_indices(n, rebalance)

    for t in range(n):
        total = cash + float(units @ prices[t])
        if t == 0 or t in rebal:
            target = weights * total
            current = units * prices[t]
            turnover = float(np.abs(target - current).sum())  # entry: from cash = total
            fee = min(fee_rate * turnover, total)
            total -= fee
            units = (weights * total) / prices[t]
            cash = 0.0
            fees_total += fee
        equity[t] = total
    return equity, fees_total


def _evaluate(
    alloc: Allocation,
    months: list[tuple[int, int]],
    dates: list[dt.date],
    series: dict[str, np.ndarray],
    cfg: BacktestConfig,
    rf_cagr: float,
    inflation: float,
    bench_returns: np.ndarray | None,
) -> dict:
    refs, weights = alloc.normalized()
    prices = np.column_stack([series[r] for r in refs])
    fee_rate = cfg.fee_percent / 100.0

    equity_net, fees = simulate(prices, weights, cfg.amount, fee_rate, cfg.rebalance)
    equity_gross, _ = simulate(prices, weights, cfg.amount, 0.0, cfg.rebalance)
    r_net = risk.monthly_returns(equity_net)

    metrics = {
        "cagr": risk.cagr(equity_net),
        "annual_return": risk.annual_return_arith(r_net),
        "volatility": risk.annual_volatility(r_net),
        "sharpe": risk.sharpe_ratio(equity_net, rf_cagr),
        "max_drawdown": risk.max_drawdown(equity_net),
        "var": risk.var_table(r_net),
        "inflation": inflation,
        "final_gross": float(equity_gross[-1]),
        "final_net": float(equity_net[-1]),
        "fees_total": fees,
    }

    relative = None
    if bench_returns is not None and bench_returns.size == r_net.size and r_net.size:
        bw = risk.best_worst_relative(r_net, bench_returns, dates)
        relative = {
            "tracking_error": risk.tracking_error(r_net, bench_returns),
            "up_capture": risk.capture_ratio(r_net, bench_returns, upside=True),
            "down_capture": risk.capture_ratio(r_net, bench_returns, upside=False),
            "best_relative_month": bw["best"],
            "worst_relative_month": bw["worst"],
        }

    return {
        "name": alloc.name,
        "weights": {r: round(float(w) * 100, 2) for r, w in zip(refs, weights)},
        "equity_gross": equity_gross,
        "equity_net": equity_net,
        "returns_net": r_net,
        "drawdown": risk.drawdown_series(equity_net),
        "calendar_years": risk.calendar_year_returns(dates, equity_net),
        "metrics": metrics,
        "relative": relative,
    }


def run_backtest(allocations: list[Allocation], cfg: BacktestConfig) -> dict:
    """Backtest several allocations (and an optional benchmark) over their common
    monthly period. Returns the shared date axis, the per-allocation reports and the
    benchmark report (computed identically, without relative metrics)."""
    if not allocations:
        raise MarketError("Au moins une allocation est requise.")
    if cfg.rebalance not in REBALANCE_CHOICES:
        raise MarketError(f"Rééquilibrage inconnu : {cfg.rebalance}.")
    if cfg.amount <= 0:
        raise MarketError("Le montant initial doit être positif.")

    refs: set[str] = set()
    for a in allocations:
        refs |= set(a.weights)
    if cfg.benchmark:
        refs |= set(cfg.benchmark.weights)
    cash_ref = f"asset:{CASH_CODE[cfg.currency]}"
    cpi_ref = f"asset:{CPI_CODE[cfg.currency]}"
    refs |= {cash_ref, cpi_ref}

    months, series = align(sorted(refs), cfg.currency, cfg.start, cfg.end)
    dates = [month_end(m) for m in months]

    rf_cagr = risk.cagr(series[cash_ref])
    inflation = risk.cagr(series[cpi_ref])

    benchmark = None
    bench_returns = None
    if cfg.benchmark:
        benchmark = _evaluate(cfg.benchmark, months, dates, series, cfg, rf_cagr, inflation, None)
        bench_returns = benchmark["returns_net"]

    results = [
        _evaluate(a, months, dates, series, cfg, rf_cagr, inflation, bench_returns)
        for a in allocations
    ]

    return {
        "currency": cfg.currency,
        "start": dates[0],
        "end": dates[-1],
        "months": len(dates),
        "rebalance": cfg.rebalance,
        "fee_percent": cfg.fee_percent,
        "rf_cagr": rf_cagr,
        "inflation": inflation,
        "dates": dates,
        "results": results,
        "benchmark": benchmark,
    }
