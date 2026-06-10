import datetime as dt
from decimal import Decimal

import pytest
import responses

from commodities import services
from commodities.datasources.commodities_api import CommoditiesApiProvider
from commodities.models import Commodity, ImportRun, PriceQuote

pytestmark = pytest.mark.django_db

LATEST_URL = "https://api.commodities-api.com/api/latest"
TIMESERIES_URL = "https://api.commodities-api.com/api/timeseries"


def make_commodity(name, symbol, **kwargs):
    return Commodity.objects.create(
        name=name, slug=name.lower(), symbol=symbol, price_symbol=symbol, **kwargs
    )


def mock_latest(rates, date="2024-06-09"):
    responses.add(
        responses.GET,
        LATEST_URL,
        json={"success": True, "date": date, "base": "USD", "rates": rates},
        status=200,
    )


@responses.activate
def test_provider_parses_and_converts(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    mock_latest({"ALU": 0.0004, "XAU": 0.0005, "EUR": 0.9})
    alu = make_commodity("Aluminium", "ALU")
    au = make_commodity("Or", "XAU")

    results = {p.commodity.symbol: p for p in CommoditiesApiProvider().fetch_latest([alu, au])}

    # price_usd = 1 / rate ; price_eur = price_usd * (EUR per USD)
    assert results["ALU"].price_usd == Decimal("2500.0000")
    assert results["ALU"].price_eur == Decimal("2250.0000")
    assert results["XAU"].price_usd == Decimal("2000.0000")
    assert results["XAU"].price_eur == Decimal("1800.0000")
    assert str(results["ALU"].date) == "2024-06-09"
    assert results["ALU"].source == "commodities_api"


@responses.activate
def test_provider_skips_uncovered_symbol(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    mock_latest({"ALU": 0.0004, "EUR": 0.9})  # cobalt (LCO) absent from upstream
    alu = make_commodity("Aluminium", "ALU")
    cobalt = make_commodity("Cobalt", "LCO")

    results = CommoditiesApiProvider().fetch_latest([alu, cobalt])

    assert {p.commodity.symbol for p in results} == {"ALU"}


@responses.activate
def test_provider_without_eur_leaves_price_eur_none(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    mock_latest({"ALU": 0.0004})
    alu = make_commodity("Aluminium", "ALU")

    [result] = CommoditiesApiProvider().fetch_latest([alu])

    assert result.price_usd == Decimal("2500.0000")
    assert result.price_eur is None


def test_provider_raises_without_api_key(settings):
    settings.COMMODITIES_API_KEY = ""
    alu = make_commodity("Aluminium", "ALU")
    with pytest.raises(RuntimeError, match="COMMODITIES_API_KEY"):
        CommoditiesApiProvider().fetch_latest([alu])


@responses.activate
def test_update_prices_service_creates_quotes_and_is_idempotent(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    mock_latest({"ALU": 0.0004, "LCO": 0.00002, "XAU": 0.0005, "EUR": 0.9})
    make_commodity("Aluminium", "ALU")
    make_commodity("Cobalt", "LCO")
    make_commodity("Or", "XAU")

    run = services.update_prices()
    assert run.status == ImportRun.Status.SUCCESS
    assert PriceQuote.objects.count() == 3
    assert "3 cours créés" in run.message

    # Re-run same day → updates in place, no duplicates.
    run2 = services.update_prices()
    assert run2.status == ImportRun.Status.SUCCESS
    assert PriceQuote.objects.count() == 3
    assert "3 mis à jour" in run2.message


@responses.activate
def test_update_prices_service_records_error(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    responses.add(responses.GET, LATEST_URL, json={"success": False, "error": "boom"}, status=200)
    make_commodity("Aluminium", "ALU")

    run = services.update_prices()

    assert run.status == ImportRun.Status.ERROR
    assert "boom" in run.message
    assert PriceQuote.objects.count() == 0


@responses.activate
def test_provider_fetch_timeseries_parses_dates(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    responses.add(
        responses.GET,
        TIMESERIES_URL,
        json={
            "success": True,
            "rates": {
                "2024-06-01": {"ALU": 0.0004, "EUR": 0.9},
                "2024-06-02": {"ALU": 0.0005, "EUR": 0.9},
            },
        },
        status=200,
    )
    alu = make_commodity("Aluminium", "ALU")

    results = {
        str(p.date): p
        for p in CommoditiesApiProvider().fetch_timeseries(
            [alu], dt.date(2024, 6, 1), dt.date(2024, 6, 2)
        )
    }

    assert results["2024-06-01"].price_usd == Decimal("2500.0000")
    assert results["2024-06-01"].price_eur == Decimal("2250.0000")
    assert results["2024-06-02"].price_usd == Decimal("2000.0000")


@responses.activate
def test_backfill_prices_service_creates_history(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    responses.add(
        responses.GET,
        TIMESERIES_URL,
        json={
            "success": True,
            "rates": {
                "2024-06-01": {"ALU": 0.0004, "EUR": 0.9},
                "2024-06-02": {"ALU": 0.0005, "EUR": 0.9},
            },
        },
        status=200,
    )
    make_commodity("Aluminium", "ALU")

    run = services.backfill_prices(days=10)

    assert run.status == ImportRun.Status.SUCCESS
    assert PriceQuote.objects.count() == 2
    assert "2 cours créés" in run.message
