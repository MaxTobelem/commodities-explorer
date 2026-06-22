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


def test_buy_amount_is_fees_inclusive():
    """A buy `amount` is the **total** cash committed (fees included): invested + fee
    equals the amount exactly, so 1000 € with 1000 € of cash never overdraws."""
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    deposit(pf, dt.date(2024, 6, 1), 1000)
    txn = buy(pf, c, dt.date(2024, 6, 1), 1000)  # exactly all the cash
    assert txn.amount + txn.fee == Decimal("1000.00")  # total out == amount asked
    assert txn.amount == Decimal("998.00")  # 1000 / 1.002, rounded
    assert txn.fee == Decimal("2.00")
    assert txn.quantity == Decimal("998.00") / Decimal("2300")
    # cash is fully spent, no overdraw error
    assert services.value_portfolio(pf, dt.date(2024, 6, 1))["cash"] == Decimal("0.00")


def test_split_gross_buy_with_fixed_fee():
    pf = make_portfolio(fee_percent="0.20", fee_fixed="1")
    invested, fee = services.split_gross_buy(pf, Decimal("1000"))
    assert invested + fee == Decimal("1000")
    assert invested == Decimal("997.01")  # (1000 - 1) / 1.002
    assert fee == Decimal("2.99")


def test_buy_snapshots_quantity_price_fee():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio(currency="EUR", fee_percent="0")  # no fee → amount == invested
    deposit(pf, dt.date(2024, 6, 1), 1000)
    txn = buy(pf, c, dt.date(2024, 6, 2), 500)  # carry-forward price 2300 EUR
    assert txn.unit_price == Decimal("2300")
    assert txn.quantity == Decimal("500") / Decimal("2300")
    assert txn.fee == Decimal("0.00")


def test_value_portfolio_unrealized_pnl_and_cash():
    c = make_commodity(quotes={
        dt.date(2024, 6, 1): (2500, 2300, DAILY),
        dt.date(2024, 6, 10): (2750, 2530, DAILY),  # +10%
    })
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    deposit(pf, dt.date(2024, 6, 1), 1000)
    buy(pf, c, dt.date(2024, 6, 2), 500)  # gross 500 → invested 499 + fee 1

    v = services.value_portfolio(pf, dt.date(2024, 6, 10))
    cents = Decimal("0.01")
    assert v["cash"] == Decimal("500.00")  # 1000 - 500 (gross, fees included)
    assert v["positions_value"].quantize(cents) == Decimal("548.90")  # 499 grown +10%
    assert v["total_value"].quantize(cents) == Decimal("1048.90")
    assert v["unrealized_pnl"].quantize(cents) == Decimal("48.90")  # 548.90 - 500 cost
    assert v["total_pnl"].quantize(cents) == Decimal("48.90")
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
    txn = buy(pf, c, dt.date(2024, 6, 2), 500)  # gross 500 → invested 499 + fee 1
    # sell the whole position on 06-10
    sell = services.prepare_transaction(
        pf, kind=Transaction.Kind.SELL, date=dt.date(2024, 6, 10),
        commodity=c, quantity=txn.quantity,
    )
    sell.save()
    assert sell.amount == Decimal("548.90")  # qty * 2530
    v = services.value_portfolio(pf, dt.date(2024, 6, 10))
    assert v["positions"] == []
    # proceeds 548.90 - 1.10 fee = 547.80 ; realized = 547.80 - 500 cost = 47.80
    assert v["realized_pnl"] == Decimal("47.80")
    assert v["cash"] == Decimal("1047.80")
    assert v["total_pnl"] == Decimal("47.80")


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


# --- invest from an asset page (deposit-if-needed + buy) --------------------


def test_invest_quote_reports_shortfall_on_empty_portfolio():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio(currency="EUR", fee_percent="0.20")  # no cash yet
    q = services.invest_quote(pf, c, dt.date(2024, 6, 1), Decimal("1000"))
    assert q["total"] == Decimal("1000")
    assert q["invested"] == Decimal("998.00")
    assert q["fee"] == Decimal("2.00")
    assert q["cash"] == Decimal("0.00")
    assert q["shortfall"] == Decimal("1000")  # nothing in the portfolio


def test_invest_auto_deposit_tops_up_then_buys():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    created = services.invest(pf, c, dt.date(2024, 6, 1), Decimal("1000"), auto_deposit=True)
    assert [t.kind for t in created] == ["deposit", "buy"]
    assert created[0].amount == Decimal("1000.00")  # exactly the shortfall
    v = services.value_portfolio(pf, dt.date(2024, 6, 1))
    assert v["cash"] == Decimal("0.00")  # deposit lands the buy cash-neutral
    assert len(v["positions"]) == 1


def test_invest_partial_shortfall_only_deposits_the_gap():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    deposit(pf, dt.date(2024, 6, 1), 400)  # already has 400
    created = services.invest(pf, c, dt.date(2024, 6, 1), Decimal("1000"), auto_deposit=True)
    assert created[0].kind == "deposit"
    assert created[0].amount == Decimal("600.00")  # only the missing 600
    assert services.value_portfolio(pf, dt.date(2024, 6, 1))["cash"] == Decimal("0.00")


def test_invest_without_auto_deposit_is_rejected_when_short():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    with pytest.raises(services.PortfolioError, match="manque"):
        services.invest(pf, c, dt.date(2024, 6, 1), Decimal("1000"), auto_deposit=False)
    assert not pf.transactions.exists()  # nothing persisted


def test_invest_uses_existing_cash_without_depositing():
    c = make_commodity(quotes={dt.date(2024, 6, 1): (2500, 2300, DAILY)})
    pf = make_portfolio(currency="EUR", fee_percent="0.20")
    deposit(pf, dt.date(2024, 6, 1), 1000)
    created = services.invest(pf, c, dt.date(2024, 6, 1), Decimal("1000"), auto_deposit=True)
    assert [t.kind for t in created] == ["buy"]  # no deposit needed
    assert services.value_portfolio(pf, dt.date(2024, 6, 1))["cash"] == Decimal("0.00")


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
