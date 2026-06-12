import datetime as dt
import io
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import openpyxl
import pytest
import responses
from django.core.management import call_command

from commodities import services
from commodities.datasources.commodities_api import CommoditiesApiProvider
from commodities.datasources.usgs_price import UsgsPriceProvider
from commodities.datasources.worldbank import WorldBankProvider
from commodities.models import Commodity, ImportRun, PriceQuote

pytestmark = pytest.mark.django_db

LATEST_URL = "https://api.commodities-api.com/api/latest"
TIMESERIES_URL = "https://api.commodities-api.com/api/timeseries"


def make_commodity(name, symbol, **kwargs):
    # api_symbol defaults to the same ticker so Commodities-API tests resolve it;
    # pass api_symbol="" to exercise the World Bank fallback lane.
    kwargs.setdefault("api_symbol", symbol)
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
    # XAU (USD/ozt) and WHEAT (USD/t) are already canonical → unit factor 1.
    mock_latest({"XAU": 0.0005, "WHEAT": 0.004, "EUR": 0.9})
    au = make_commodity("Or", "XAU")
    wheat = make_commodity("Blé", "WHEAT")

    results = {p.commodity.symbol: p for p in CommoditiesApiProvider().fetch_latest([au, wheat])}

    # price_usd = 1 / rate ; price_eur = price_usd * (EUR per USD)
    assert results["XAU"].price_usd == Decimal("2000.0000")
    assert results["XAU"].price_eur == Decimal("1800.0000")
    assert results["WHEAT"].price_usd == Decimal("250.0000")
    assert results["WHEAT"].price_eur == Decimal("225.0000")
    assert str(results["XAU"].date) == "2024-06-09"
    assert results["XAU"].source == "commodities_api"


@responses.activate
def test_provider_applies_unit_factor(settings):
    """Per-symbol unit normalisation: metals troy-oz→tonne, softs lb/cents→kg."""
    settings.COMMODITIES_API_KEY = "test-key"
    # XCU (per troy ounce), SUGAR (USD/lb), COFFEE (US cents/lb).
    mock_latest({"XCU": 2.5, "SUGAR": 7.0, "COFFEE": 0.5})
    cu = make_commodity("Cuivre", "XCU", price_unit="USD/t")
    sugar = make_commodity("Sucre", "SUGAR", price_unit="USD/kg")
    coffee = make_commodity("Café", "COFFEE", price_unit="USD/kg")

    res = {p.commodity.symbol: p for p in CommoditiesApiProvider().fetch_latest([cu, sugar, coffee])}

    assert res["XCU"].price_usd == Decimal("12860.2986")  # 0.4 USD/ozt × 32150.7466
    assert res["SUGAR"].price_usd == Decimal("0.3149")  # 0.142857 USD/lb × 2.2046226
    assert res["COFFEE"].price_usd == Decimal("0.0441")  # 2.0 cents/lb × 2.2046226 / 100


@responses.activate
def test_provider_skips_uncovered_symbol(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    mock_latest({"ALU": 0.0004, "EUR": 0.9})  # cobalt (LCO) absent from upstream
    alu = make_commodity("Aluminium", "ALU")
    cobalt = make_commodity("Cobalt", "LCO")

    results = CommoditiesApiProvider().fetch_latest([alu, cobalt])

    assert {p.commodity.symbol for p in results} == {"ALU"}


@responses.activate
def test_provider_chunks_requests_by_symbol_cap(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    settings.COMMODITIES_API_MAX_SYMBOLS = 2  # 1 commodity + EUR per request
    mock_latest({"ALU": 0.0004, "XAU": 0.0005, "EUR": 0.9})
    alu = make_commodity("Aluminium", "ALU")
    au = make_commodity("Or", "XAU")

    results = {p.commodity.symbol: p for p in CommoditiesApiProvider().fetch_latest([alu, au])}

    assert set(results) == {"ALU", "XAU"}
    assert len(responses.calls) == 2  # two symbols split into two capped requests


@responses.activate
def test_provider_without_eur_leaves_price_eur_none(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    mock_latest({"XAU": 0.0005})
    au = make_commodity("Or", "XAU")

    [result] = CommoditiesApiProvider().fetch_latest([au])

    assert result.price_usd == Decimal("2000.0000")
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
def test_update_prices_falls_back_to_worldbank_when_api_misses(settings):
    """A ticker the daily API doesn't return is gap-filled by the monthly source."""
    settings.COMMODITIES_API_KEY = "test-key"
    settings.WORLD_BANK_XLSX_URL = "http://test/cmo.xlsx"
    settings.EUR_USD_RATE = "0.9"
    mock_latest({"ALU": 0.0004, "EUR": 0.9})  # API covers ALU but not 'Gold'
    responses.add(responses.GET, "http://test/cmo.xlsx", body=_wb_xlsx_bytes(), status=200)
    make_commodity("Aluminium", "ALU", price_provider="worldbank")
    make_commodity("Or", "Gold", price_provider="worldbank")  # api_symbol 'Gold' not upstream

    run = services.update_prices()

    assert run.status == ImportRun.Status.SUCCESS
    by_name = {q.commodity.name: q for q in PriceQuote.objects.select_related("commodity")}
    assert by_name["Aluminium"].source == "commodities_api"  # daily lane
    assert by_name["Or"].source == "worldbank"  # gap-filled monthly lane


@responses.activate
def test_check_api_symbols_reports_valid_invalid_and_blank(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    # The live /symbols endpoint returns the {symbol: name} map at the JSON root.
    responses.add(
        responses.GET,
        "https://api.commodities-api.com/api/symbols",
        json={"XAU": "Gold", "BRENTOIL": "Brent Crude Oil"},
        status=200,
    )
    make_commodity("Or", "XAU", api_symbol="XAU")  # valid
    make_commodity("Cuivre", "CU", api_symbol="NOPE")  # invalid ticker
    make_commodity("Thé", "THE", api_symbol="")  # blank → monthly only

    out = io.StringIO()
    call_command("check_api_symbols", stdout=out)
    text = out.getvalue()

    assert "Or: XAU" in text
    assert "NOPE" in text  # invalid flagged
    assert "Thé" in text  # blank listed
    assert "BRENTOIL" in text  # supported-but-unused suggestion


@responses.activate
def test_check_api_symbols_handles_wrapped_symbols_shape(settings):
    """The older/wrapped shape ({"symbols": {...}}) is still supported."""
    settings.COMMODITIES_API_KEY = "test-key"
    responses.add(
        responses.GET,
        "https://api.commodities-api.com/api/symbols",
        json={"success": True, "symbols": {"XAU": "Gold"}},
        status=200,
    )
    make_commodity("Or", "XAU", api_symbol="XAU")

    out = io.StringIO()
    call_command("check_api_symbols", stdout=out)

    assert "Or: XAU" in out.getvalue()


@responses.activate
def test_provider_fetch_timeseries_parses_dates(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    responses.add(
        responses.GET,
        TIMESERIES_URL,
        json={
            "success": True,
            "rates": {
                "2024-06-01": {"XAU": 0.0005, "EUR": 0.9},
                "2024-06-02": {"XAU": 0.0004, "EUR": 0.9},
            },
        },
        status=200,
    )
    au = make_commodity("Or", "XAU")

    results = {
        str(p.date): p
        for p in CommoditiesApiProvider().fetch_timeseries(
            [au], dt.date(2024, 6, 1), dt.date(2024, 6, 2)
        )
    }

    assert results["2024-06-01"].price_usd == Decimal("2000.0000")
    assert results["2024-06-01"].price_eur == Decimal("1800.0000")
    assert results["2024-06-02"].price_usd == Decimal("2500.0000")


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
    assert "2 cours importés" in run.message


@responses.activate
def test_provider_fetch_timeseries_one_symbol_per_request(settings):
    """Upstream allows a single symbol per timeseries call → one request per symbol (+ EUR)."""
    settings.COMMODITIES_API_KEY = "test-key"
    responses.add(
        responses.GET,
        TIMESERIES_URL,
        json={
            "success": True,
            "rates": {"2024-06-01": {"XAU": 0.0005, "WHEAT": 0.004, "EUR": 0.9}},
        },
        status=200,
    )
    au = make_commodity("Or", "XAU")
    wheat = make_commodity("Blé", "WHEAT")

    results = {
        p.commodity.symbol: p
        for p in CommoditiesApiProvider().fetch_timeseries(
            [au, wheat], dt.date(2024, 6, 1), dt.date(2024, 6, 1)
        )
    }

    assert len(responses.calls) == 3  # EUR + XAU + WHEAT, one symbol per request
    assert results["XAU"].price_usd == Decimal("2000.0000")
    assert results["WHEAT"].price_usd == Decimal("250.0000")


@responses.activate
def test_backfill_daily_service_imports_commodities_api_history(settings):
    settings.COMMODITIES_API_KEY = "test-key"
    responses.add(
        responses.GET,
        TIMESERIES_URL,
        json={
            "success": True,
            "rates": {
                "2024-06-01": {"XAU": 0.0005, "EUR": 0.9},
                "2024-06-02": {"XAU": 0.0004, "EUR": 0.9},
            },
        },
        status=200,
    )
    make_commodity("Or", "XAU")  # daily lane
    make_commodity("Thé", "THE", api_symbol="")  # no api_symbol → excluded

    run = services.backfill_daily(days=10)

    assert run.status == ImportRun.Status.SUCCESS
    assert PriceQuote.objects.filter(source="commodities_api").count() == 2
    assert "cours Commodities-API importés" in run.message


@responses.activate
def test_provider_fetch_timeseries_windows_long_range(settings):
    """A range beyond the plan's per-request cap is split into ≤30-day windows."""
    settings.COMMODITIES_API_KEY = "test-key"
    settings.COMMODITIES_API_TIMESERIES_MAX_DAYS = 30
    responses.add(
        responses.GET,
        TIMESERIES_URL,
        json={"success": True, "rates": {"2024-06-01": {"XAU": 0.0005, "EUR": 0.9}}},
        status=200,
    )
    au = make_commodity("Or", "XAU")

    # 70-day span → 3 windows, fetched for EUR and XAU → 6 requests, none over the cap.
    CommoditiesApiProvider().fetch_timeseries([au], dt.date(2024, 6, 1), dt.date(2024, 8, 10))

    assert len(responses.calls) == 6
    for call in responses.calls:
        q = parse_qs(urlparse(call.request.url).query)
        span = dt.date.fromisoformat(q["end_date"][0]) - dt.date.fromisoformat(q["start_date"][0])
        assert span.days <= 30


@responses.activate
def test_provider_surfaces_api_error_body(settings):
    """A failed call raises the API's own error (timeframe_too_long), not a bare HTTP 400."""
    settings.COMMODITIES_API_KEY = "test-key"
    responses.add(
        responses.GET,
        TIMESERIES_URL,
        json={"success": False, "error": {"code": 400, "type": "timeframe_too_long", "info": "x"}},
        status=400,
    )
    au = make_commodity("Or", "XAU")

    with pytest.raises(RuntimeError, match="timeframe_too_long"):
        CommoditiesApiProvider().fetch_timeseries([au], dt.date(2024, 1, 1), dt.date(2024, 1, 2))


def _wb_xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monthly Prices"
    ws.append(["World Bank Commodity Price Data"])
    ws.append(["monthly prices"])
    ws.append(["(monthly series)"])
    ws.append(["Updated on ..."])
    ws.append([None, "Aluminum", "Gold"])  # row 5: commodity names
    ws.append([None, "($/mt)", "($/troy oz)"])  # row 6: units
    ws.append(["2025M11", 2800, 4000])
    ws.append(["2025M12", 2875.53, 4309.23])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@responses.activate
def test_worldbank_provider_fetch_latest(settings):
    settings.WORLD_BANK_XLSX_URL = "http://test/cmo.xlsx"
    settings.EUR_USD_RATE = "0.9"
    responses.add(responses.GET, "http://test/cmo.xlsx", body=_wb_xlsx_bytes(), status=200)
    alu = make_commodity("Aluminium", "Aluminum")
    au = make_commodity("Or", "Gold")

    results = {p.commodity.price_symbol: p for p in WorldBankProvider().fetch_latest([alu, au])}

    assert results["Aluminum"].price_usd == Decimal("2875.5300")
    assert results["Aluminum"].price_eur == Decimal("2587.9770")  # × 0.9
    assert results["Gold"].price_usd == Decimal("4309.2300")
    assert str(results["Aluminum"].date) == "2025-12-01"


@responses.activate
def test_usgs_price_provider_cobalt_per_tonne():
    item_url = "https://www.sciencebase.gov/catalog/item/6797fb00d34ea8c18376e159"
    salient_url = "http://test/cobalt_salient.csv"
    responses.add(
        responses.GET,
        item_url,
        json={"files": [{"name": "mcs2025-cobal_salient.csv", "downloadUri": salient_url}]},
        status=200,
    )
    responses.add(
        responses.GET,
        salient_url,
        body="Year,Price_Spot_dlb,Price_LME_dlb\n2023,17.2,15.48\n2024,17.0,12.0\n",
        status=200,
    )
    cobalt = make_commodity("Cobalt", "Cobalt")

    results = UsgsPriceProvider().fetch_latest([cobalt])

    assert len(results) == 1
    assert results[0].date == dt.date(2024, 7, 1)  # latest year
    assert results[0].price_usd == (Decimal("17.0") * Decimal("2204.62262")).quantize(Decimal("0.0001"))
