"""Engine tests (DB-backed): CSV import, FX conversion, period alignment, the
gross/net fee model, rebalancing, multi-allocation + benchmark, and a mixed
commodity+index backtest."""

from decimal import Decimal

import pytest

from commodities.models import Commodity, PriceQuote
from markets import services
from markets.backtest import Allocation, BacktestConfig, run_backtest, simulate
from markets.catalog import MarketAsset
from markets.management.commands.import_market_assets import import_all
from markets.models import AssetPrice
from markets.services import month_end

pytestmark = pytest.mark.django_db

A = MarketAsset.AssetClass


def gen_months(start: tuple[int, int], n: int) -> list[tuple[int, int]]:
    out, (y, m) = [], start
    for _ in range(n):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def mk_asset(code, asset_class, currency, series: dict[tuple[int, int], float]):
    a = MarketAsset.objects.create(code=code, name=code, asset_class=asset_class, currency=currency)
    AssetPrice.objects.bulk_create(
        [AssetPrice(asset=a, date=month_end(ym), value=Decimal(str(v))) for ym, v in series.items()]
    )
    return a


def seed_aux(months, *, usd=True, eur=True, fx_rate=1.25):
    """Create the cash / CPI / FX series the engine needs over ``months``."""
    if usd:
        mk_asset("SBWMUD1L", A.CASH, "USD", {m: 100 + i for i, m in enumerate(months)})
        mk_asset("USCPI", A.CPI, "USD", {m: 100 + 0.5 * i for i, m in enumerate(months)})
    if eur:
        mk_asset("SBWMEU1L", A.CASH, "EUR", {m: 100 + i for i, m in enumerate(months)})
        mk_asset("EUCPI", A.CPI, "EUR", {m: 100 + 0.4 * i for i, m in enumerate(months)})
    mk_asset("EURBGN", A.FX, "USD", {m: fx_rate for m in months})


# --- Import -----------------------------------------------------------------


def test_import_seed_loads_real_csvs():
    stats = import_all()
    assert MarketAsset.objects.count() == len(stats)
    ndduwi = MarketAsset.objects.get(code="NDDUWI")
    assert ndduwi.asset_class == A.EQUITY and ndduwi.currency == "USD"
    first = ndduwi.prices.order_by("date").first()
    assert first.value == Decimal("100.000000")  # base 100
    assert ndduwi.prices.count() > 500  # long monthly history


# --- FX & resolution --------------------------------------------------------


def test_resolve_fx_converts_usd_and_eur():
    months = gen_months((2020, 1), 3)
    seed_aux(months, fx_rate=1.25)
    mk_asset("USTEST", A.EQUITY, "USD", {m: 200 for m in months})
    mk_asset("EUTEST", A.BOND, "EUR", {m: 200 for m in months})
    # USD asset valued in EUR → divide by 1.25; EUR asset valued in USD → ×1.25.
    assert services.resolve_monthly("asset:USTEST", "EUR")[(2020, 1)] == pytest.approx(160.0)
    assert services.resolve_monthly("asset:EUTEST", "USD")[(2020, 1)] == pytest.approx(250.0)
    assert services.resolve_monthly("asset:USTEST", "USD")[(2020, 1)] == pytest.approx(200.0)


def test_align_uses_common_overlap():
    a_months = gen_months((2019, 1), 24)
    b_months = gen_months((2020, 1), 24)
    seed_aux(gen_months((2018, 1), 60))
    mk_asset("AAA", A.EQUITY, "USD", {m: 100 for m in a_months})
    mk_asset("BBB", A.EQUITY, "USD", {m: 100 for m in b_months})
    months, series = services.align(["asset:AAA", "asset:BBB"], "USD")
    assert months[0] == (2020, 1)  # later start wins
    assert months[-1] == (2020, 12)  # earlier end wins
    assert len(series["asset:AAA"]) == len(months)


# --- Fee model (gross vs net) -----------------------------------------------


def test_gross_equals_net_with_zero_fee():
    import numpy as np

    prices = np.array([[100.0], [110.0], [121.0]])
    w = np.array([1.0])
    eq, fees = simulate(prices, w, 1000.0, 0.0, "monthly")
    assert fees == 0.0
    assert eq[-1] == pytest.approx(1210.0)


def test_net_below_gross_by_entry_fee_single_asset_buy_and_hold():
    import numpy as np

    prices = np.array([[100.0], [200.0]])
    w = np.array([1.0])
    fee_rate = 0.01  # 1 %
    net, fees = simulate(prices, w, 1000.0, fee_rate, "none")
    gross, _ = simulate(prices, w, 1000.0, 0.0, "none")
    # Only an entry fee on a buy-and-hold single asset → net = gross × (1 − fee).
    assert fees == pytest.approx(10.0)
    assert net[-1] == pytest.approx(gross[-1] * (1 - fee_rate))
    assert net[-1] == pytest.approx(1980.0)


def test_rebalancing_changes_outcome():
    import numpy as np

    # A rallies then falls; B mirrors it. Rebalancing harvests the swing.
    prices = np.array([[100.0, 100.0], [200.0, 50.0], [100.0, 100.0]])
    w = np.array([0.5, 0.5])
    none, _ = simulate(prices, w, 1000.0, 0.0, "none")
    monthly, _ = simulate(prices, w, 1000.0, 0.0, "monthly")
    assert none[-1] == pytest.approx(1000.0)  # round-trip, back to start
    assert monthly[-1] == pytest.approx(1562.5)  # buy-low/sell-high adds value
    assert monthly[-1] > none[-1]


# --- Full backtest ----------------------------------------------------------


def test_backtest_multi_allocation_and_benchmark():
    months = gen_months((2018, 1), 36)
    seed_aux(months)
    mk_asset("STOCK", A.EQUITY, "USD", {m: 100 * (1.01**i) for i, m in enumerate(months)})
    mk_asset("BONDX", A.BOND, "USD", {m: 100 * (1.002**i) for i, m in enumerate(months)})

    cfg = BacktestConfig(
        amount=1000, currency="USD", rebalance="monthly", fee_percent=0.2,
        benchmark=Allocation("100% actions", {"asset:STOCK": 100}),
    )
    res = run_backtest(
        [
            Allocation("60/40", {"asset:STOCK": 60, "asset:BONDX": 40}),
            Allocation("Tout obligations", {"asset:BONDX": 100}),
        ],
        cfg,
    )
    assert len(res["dates"]) == 36
    assert len(res["results"]) == 2
    assert res["benchmark"]["relative"] is None  # benchmark has no relative block
    r0 = res["results"][0]
    assert r0["relative"] is not None
    assert set(r0["metrics"]["var"].keys()) == {"90", "95", "98", "99"}
    # Net is never above gross.
    assert r0["metrics"]["final_net"] <= r0["metrics"]["final_gross"]
    assert r0["metrics"]["fees_total"] > 0


def test_backtest_currency_consistency_with_constant_fx():
    months = gen_months((2019, 1), 24)
    seed_aux(months, fx_rate=1.25)
    mk_asset("GLD", A.EQUITY, "USD", {m: 100 * (1.005**i) for i, m in enumerate(months)})
    alloc = Allocation("Or", {"asset:GLD": 100})
    usd = run_backtest([alloc], BacktestConfig(amount=1000, currency="USD", rebalance="none", fee_percent=0))
    eur = run_backtest([alloc], BacktestConfig(amount=1000, currency="EUR", rebalance="none", fee_percent=0))
    # A constant FX only rescales the series, so the allocation CAGR is identical.
    assert usd["results"][0]["metrics"]["cagr"] == pytest.approx(eur["results"][0]["metrics"]["cagr"])


def test_backtest_mixes_commodity_and_index():
    months = gen_months((2020, 1), 12)
    seed_aux(months)
    mk_asset("EQ", A.EQUITY, "USD", {m: 100 * (1.01**i) for i, m in enumerate(months)})
    gold = Commodity.objects.create(name="Or", slug="gold")
    PriceQuote.objects.bulk_create(
        [
            PriceQuote(commodity=gold, date=month_end(m), price_usd=Decimal(str(1800 + 10 * i)), source="wb")
            for i, m in enumerate(months)
        ]
    )
    res = run_backtest(
        [Allocation("Mix", {"commodity:gold": 50, "asset:EQ": 50})],
        BacktestConfig(amount=1000, currency="USD", rebalance="monthly", fee_percent=0.2),
    )
    assert res["results"][0]["weights"] == {"commodity:gold": 50.0, "asset:EQ": 50.0}
    assert len(res["dates"]) == 12
    assert res["results"][0]["metrics"]["final_net"] > 0
