import datetime as dt
from decimal import Decimal

import pytest

from commodities.models import Commodity, PriceQuote
from portfolios import services
from portfolios.models import Portfolio, Transaction

pytestmark = pytest.mark.django_db

DAILY = "commodities_api"  # services.DAILY_PRICE_SOURCE


def make_commodity(slug="aluminium", quotes=None):
    """quotes: {date: (price_usd, price_eur, source)}."""
    c = Commodity.objects.create(name=slug.title(), slug=slug)
    for date, (usd, eur, src) in (quotes or {}).items():
        PriceQuote.objects.create(
            commodity=c, date=date,
            price_usd=Decimal(str(usd)),
            price_eur=None if eur is None else Decimal(str(eur)),
            source=src,
        )
    return c


def make_portfolio(currency="EUR", fee_percent="0.20", fee_fixed="0"):
    user = pytest.importorskip("django.contrib.auth").get_user_model().objects.create_user(
        "u", "u@e.com", "x"
    )
    return Portfolio.objects.create(
        user=user, name="Test", base_currency=currency,
        fee_percent=Decimal(fee_percent), fee_fixed=Decimal(fee_fixed),
    )


def buy(pf, commodity, date, amount):
    txn = services.prepare_transaction(
        pf, kind=Transaction.Kind.BUY, date=date, commodity=commodity, amount=Decimal(str(amount))
    )
    txn.save()
    return txn


def deposit(pf, date, amount):
    txn = services.prepare_transaction(
        pf, kind=Transaction.Kind.DEPOSIT, date=date, amount=Decimal(str(amount))
    )
    txn.save()
    return txn


# --- price_at / currency ----------------------------------------------------


def test_price_at_carry_forward_and_currency():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    # exact date
    assert services.price_at(c, dt.date(2024, 6, 1), "EUR") == Decimal("2300")
    assert services.price_at(c, dt.date(2024, 6, 1), "USD") == Decimal("2500")
    # carry-forward to a later date with no quote
    assert services.price_at(c, dt.date(2024, 6, 15), "EUR") == Decimal("2300")
    # before the first quote → None
    assert services.price_at(c, dt.date(2024, 5, 1), "EUR") is None


def test_price_at_fx_fallback_when_eur_missing(settings):
    settings.EUR_USD_RATE = "0.9"
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, None, DAILY)})
    assert services.price_at(c, dt.date(2024, 6, 1), "EUR") == Decimal("2250.0")


def test_compute_fee_percent_and_fixed():
    pf = make_portfolio(fee_percent="0.20", fee_fixed="1")
    assert services.compute_fee(pf, Decimal("1000")) == Decimal("3.00")  # 0.2% of 1000 + 1


# --- buy / valuation / P&L --------------------------------------------------


def test_buy_snapshots_quantity_price_fee():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    deposit(pf, dt.date(2024, 6, 1), 1000)
    txn = buy(pf, c, dt.date(2024, 6, 2), 500)  # carry-forward price 2300 EUR
    assert txn.unit_price == Decimal("2300")
    assert txn.quantity == Decimal("500") / Decimal("2300")
    assert txn.fee == Decimal("1.00")  # 0.2% of 500


def test_value_portfolio_unrealized_pnl_and_cash():
    c = make_commodity(quotes={
        dt.date(2024, 6, 1): (2500, 2300, DAILY),
        dt.date(2024, 6, 10): (2750, 2530, DAILY),  # +10%
    })
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    deposit(pf, dt.date(2024, 6, 1), 1000)
    buy(pf, c, dt.date(2024, 6, 2), 500)  # cost 500 + 1 fee = 501

    v = services.value_portfolio(pf, dt.date(2024, 6, 10))
    cents = Decimal("0.01")
    assert v["cash"] == Decimal("499.00")  # 1000 - 501 (exact, no qty rounding)
    assert v["positions_value"].quantize(cents) == Decimal("550.00")  # 500 grown +10%
    assert v["total_value"].quantize(cents) == Decimal("1049.00")
    assert v["unrealized_pnl"].quantize(cents) == Decimal("49.00")  # 550 - 501
    assert v["total_pnl"].quantize(cents) == Decimal("49.00")
    assert v["fees_total"] == Decimal("1.00")
    assert len(v["positions"]) == 1
    assert v["positions"][0]["weight"] == Decimal("100")


def test_sell_realizes_pnl():
    c = make_commodity(quotes={
        dt.date(2024, 6, 1): (2500, 2300, DAILY),
        dt.date(2024, 6, 10): (2750, 2530, DAILY),
    })
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    deposit(pf, dt.date(2024, 6, 1), 1000)
    txn = buy(pf, c, dt.date(2024, 6, 2), 500)
    # sell the whole position on 06-10
    sell = services.prepare_transaction(
        pf, kind=Transaction.Kind.SELL, date=dt.date(2024, 6, 10),
        commodity=c, quantity=txn.quantity,
    )
    sell.save()
    assert sell.amount == Decimal("550.00")  # qty * 2530
    v = services.value_portfolio(pf, dt.date(2024, 6, 10))
    assert v["positions"] == []
    # proceeds 550 - 1.10 fee = 548.90 ; realized = 548.90 - 501 cost = 47.90
    assert v["realized_pnl"] == Decimal("47.90")
    assert v["cash"] == Decimal("1047.90")
    assert v["total_pnl"] == Decimal("47.90")


# --- rules ------------------------------------------------------------------


def test_buy_without_enough_cash_is_rejected():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio()
    deposit(pf, dt.date(2024, 6, 1), 100)
    with pytest.raises(services.PortfolioError):
        buy(pf, c, dt.date(2024, 6, 1), 500)


def test_oversell_is_rejected():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio()
    deposit(pf, dt.date(2024, 6, 1), 1000)
    buy(pf, c, dt.date(2024, 6, 1), 200)
    with pytest.raises(services.PortfolioError):
        services.prepare_transaction(
            pf, kind=Transaction.Kind.SELL, date=dt.date(2024, 6, 1),
            commodity=c, amount=Decimal("500"),  # more than held
        )


def test_buy_on_date_without_price_is_rejected():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio()
    deposit(pf, dt.date(2024, 5, 1), 1000)
    with pytest.raises(services.PortfolioError):
        buy(pf, c, dt.date(2024, 5, 1), 100)  # before any quote


# --- monthly carry-forward + history ---------------------------------------


def test_value_uses_carry_forward_for_monthly_commodity():
    c = make_commodity(slug="the", quotes={
        dt.date(2024, 1, 31): (10, 9, "worldbank"),
        dt.date(2024, 2, 29): (12, 11, "worldbank"),
    })
    pf = make_portfolio(currency="EUR", fee_percent="0")
    deposit(pf, dt.date(2024, 1, 31), 1000)
    buy(pf, c, dt.date(2024, 2, 15), 90)  # carry-forward Jan price 9 EUR → qty 10
    v = services.value_portfolio(pf, dt.date(2024, 3, 15))  # carry-forward Feb price 11
    assert v["positions"][0]["quantity"] == Decimal("10")
    assert v["positions_value"] == Decimal("110")  # 10 * 11


def test_history_tracks_value_over_time():
    c = make_commodity(quotes={
        dt.date(2024, 6, 1): (2500, 2300, DAILY),
        dt.date(2024, 6, 10): (2750, 2530, DAILY),
    })
    pf = make_portfolio(currency="EUR", fee_percent="0")
    deposit(pf, dt.date(2024, 6, 1), 1000)
    buy(pf, c, dt.date(2024, 6, 1), 500)
    pts = services.history(pf, dt.date(2024, 6, 1), dt.date(2024, 6, 10), "daily")
    cents = Decimal("0.01")
    assert pts[0]["date"] == dt.date(2024, 6, 1)
    assert pts[0]["value"].quantize(cents) == Decimal("1000.00")  # 500 cash + 500 position
    assert pts[-1]["date"] == dt.date(2024, 6, 10)
    assert pts[-1]["value"].quantize(cents) == Decimal("1050.00")  # 500 cash + 550 position
