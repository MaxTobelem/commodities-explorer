"""Closed-form tests of the risk metrics: each formula is pinned against a value
computed by hand on a tiny synthetic series. Pure NumPy, no DB needed."""

import datetime as dt
import math

import numpy as np
import pytest

from markets import risk


def test_monthly_returns():
    assert risk.monthly_returns([100, 110, 121]) == pytest.approx([0.10, 0.10])
    assert risk.monthly_returns([100]).size == 0


def test_cagr_geometric():
    # 100 → 200 over 12 months = +100 %/yr; 100 → 400 over 24 months = +100 %/yr.
    assert risk.cagr([100] + [0] * 11 + [200]) == pytest.approx(1.0)
    assert risk.cagr(np.linspace(0, 0, 25) + np.geomspace(100, 400, 25)) == pytest.approx(1.0)


def test_annual_return_and_volatility():
    assert risk.annual_return_arith([0.01] * 6) == pytest.approx(0.12)
    # returns [0.01, 0.03]: std(ddof=1)=0.0141421, ×√12
    vol = risk.annual_volatility([0.01, 0.03])
    assert vol == pytest.approx(0.01414214 * math.sqrt(12), rel=1e-6)
    assert risk.annual_volatility([0.02]) == 0.0  # < 2 points


def test_sharpe_ratio():
    equity = [100, 90, 108]  # monthly returns -0.10, +0.20
    expected = risk.cagr(equity) / risk.annual_volatility(risk.monthly_returns(equity))
    assert risk.sharpe_ratio(equity, 0.0) == pytest.approx(expected)
    assert risk.sharpe_ratio([100, 100, 100], 0.0) == 0.0  # zero vol guard


def test_historical_var_quantile_and_scaling():
    returns = [round(-0.10 + 0.01 * k, 2) for k in range(21)]  # -0.10 … 0.10
    assert risk.historical_var(returns, 0.95) == pytest.approx(0.09)
    assert risk.historical_var(returns, 0.90) == pytest.approx(0.08)
    table = risk.var_table(returns)
    assert table["95"]["monthly"] == pytest.approx(0.09)
    assert table["95"]["annual"] == pytest.approx(0.09 * math.sqrt(12))


def test_drawdown():
    equity = [100, 120, 60, 90]
    assert risk.drawdown_series(equity) == pytest.approx([0.0, 0.0, -0.5, -0.25])
    assert risk.max_drawdown(equity) == pytest.approx(-0.5)


def test_calendar_year_returns():
    dates, equity = [], []
    # Monthly Dec-2017 … Dec-2019; year-end values 100 (2017) → 200 (2018) → 100 (2019).
    targets = {(2017, 12): 100.0, (2018, 12): 200.0, (2019, 12): 100.0}
    y, m = 2017, 12
    while (y, m) <= (2019, 12):
        dates.append(dt.date(y, m, 28))
        equity.append(targets.get((y, m), 150.0))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    assert risk.calendar_year_returns(dates, equity) == [(2018, pytest.approx(1.0)), (2019, pytest.approx(-0.5))]


def test_tracking_error():
    assert risk.tracking_error([0.05, 0.02], [0.05, 0.02]) == 0.0  # identical → 0
    te = risk.tracking_error([0.10, 0.00], [0.0, 0.0])  # active [0.10, 0.0]
    assert te == pytest.approx(0.07071068 * math.sqrt(12), rel=1e-6)


def test_capture_ratios():
    rb = [0.10, -0.10, 0.05]
    rp = [0.20, -0.05, 0.10]
    # up months (rb>0): idx 0,2 → cumP=1.2*1.1-1=0.32, cumB=1.1*1.05-1=0.155
    assert risk.capture_ratio(rp, rb, upside=True) == pytest.approx(0.32 / 0.155 * 100)
    # down months (rb<0): idx 1 → cumP=-0.05, cumB=-0.10
    assert risk.capture_ratio(rp, rb, upside=False) == pytest.approx(50.0)


def test_best_worst_relative_month():
    rb = [0.10, -0.10, 0.05]
    rp = [0.20, -0.05, 0.10]
    dates = [dt.date(2020, 1, 31), dt.date(2020, 2, 29), dt.date(2020, 3, 31), dt.date(2020, 4, 30)]
    bw = risk.best_worst_relative(rp, rb, dates)
    assert bw["best"]["value"] == pytest.approx(1.20 / 1.10 - 1)
    assert bw["best"]["date"] == dt.date(2020, 2, 29)  # returns align to dates[1:]
    assert bw["worst"]["value"] == pytest.approx(1.10 / 1.05 - 1)
