import datetime as dt
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.db import IntegrityError

from commodities.models import (
    Commodity,
    CommodityReserve,
    CommodityUsage,
    Country,
    Event,
    EventImpact,
    ImportRun,
    PriceQuote,
    Sector,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def aluminium():
    return Commodity.objects.create(
        name="Aluminium", slug="aluminium", symbol="ALU", price_symbol="ALU"
    )


def test_commodity_str(aluminium):
    assert str(aluminium) == "Aluminium"


def test_latest_quote_returns_most_recent(aluminium):
    PriceQuote.objects.create(
        commodity=aluminium, date=dt.date(2024, 1, 1), price_usd=Decimal("2000")
    )
    recent = PriceQuote.objects.create(
        commodity=aluminium, date=dt.date(2024, 6, 1), price_usd=Decimal("2500")
    )
    assert aluminium.latest_quote == recent


def test_price_quote_unique_constraint(aluminium):
    PriceQuote.objects.create(
        commodity=aluminium, date=dt.date(2024, 1, 1), price_usd=Decimal("2000"), source="api"
    )
    with pytest.raises(IntegrityError):
        PriceQuote.objects.create(
            commodity=aluminium, date=dt.date(2024, 1, 1), price_usd=Decimal("2100"), source="api"
        )


def test_price_quote_same_date_different_source_allowed(aluminium):
    PriceQuote.objects.create(
        commodity=aluminium, date=dt.date(2024, 1, 1), price_usd=Decimal("2000"), source="api"
    )
    PriceQuote.objects.create(
        commodity=aluminium, date=dt.date(2024, 1, 1), price_usd=Decimal("2000"), source="seed"
    )
    assert aluminium.prices.count() == 2


def test_reserve_unique_constraint(aluminium):
    congo = Country.objects.create(name="Congo", iso3="COD")
    CommodityReserve.objects.create(
        commodity=aluminium, country=congo, year=2024, reserves_t=Decimal("100")
    )
    with pytest.raises(IntegrityError):
        CommodityReserve.objects.create(
            commodity=aluminium, country=congo, year=2024, reserves_t=Decimal("200")
        )


def test_usage_unique_constraint(aluminium):
    sector = Sector.objects.create(name="Transport", slug="transport")
    CommodityUsage.objects.create(commodity=aluminium, sector=sector, share_percent=Decimal("35"))
    with pytest.raises(IntegrityError):
        CommodityUsage.objects.create(
            commodity=aluminium, sector=sector, share_percent=Decimal("40")
        )


def test_event_impact_relation(aluminium):
    event = Event.objects.create(
        title="Guerre", slug="guerre", type=Event.Type.WAR, start_date=dt.date(2022, 2, 24)
    )
    impact = EventImpact.objects.create(
        event=event, commodity=aluminium, direction=EventImpact.Direction.UP, magnitude=Decimal("30")
    )
    assert impact in aluminium.impacts.all()
    assert event.impacts.count() == 1


def test_import_run_finish():
    run = ImportRun.objects.create(kind=ImportRun.Kind.PRICES)
    assert run.status == ImportRun.Status.RUNNING
    assert run.finished_at is None
    run.finish(ImportRun.Status.SUCCESS, "done")
    run.refresh_from_db()
    assert run.status == ImportRun.Status.SUCCESS
    assert run.finished_at is not None
    assert run.message == "done"


def test_seed_command_is_idempotent():
    call_command("seed")
    call_command("seed")
    assert Commodity.objects.count() == 3
    assert Country.objects.count() == 12
    assert Sector.objects.count() == 8
    # Cross-relations populated
    cobalt = Commodity.objects.get(slug="cobalt")
    assert cobalt.usages.count() >= 1
    assert cobalt.production.count() >= 1
    assert cobalt.impacts.count() >= 1


def test_commodity_catalog_imports_all_categories():
    from commodities.catalog import COMMODITY_CATALOG, ensure_commodities

    n = ensure_commodities()

    assert n == len(COMMODITY_CATALOG)
    assert Commodity.objects.count() == len(COMMODITY_CATALOG)
    assert Commodity.objects.filter(category=Commodity.Category.ENERGY).exists()
    assert Commodity.objects.filter(category=Commodity.Category.AGRICULTURAL).exists()
    assert Commodity.objects.filter(category=Commodity.Category.FERTILIZER).exists()
    # Long World Bank labels are stored as price_symbol
    brent = Commodity.objects.get(slug="petrole-brut-brent")
    assert brent.price_symbol == "Crude oil, Brent"
    assert brent.price_provider == "worldbank"
    # Idempotent
    assert ensure_commodities() == len(COMMODITY_CATALOG)
    assert Commodity.objects.count() == len(COMMODITY_CATALOG)


def test_import_curated_sets_authoritative_usages():
    call_command("seed")
    call_command("import_curated")
    cobalt = Commodity.objects.get(slug="cobalt")

    usages = {u.sector.name: u for u in cobalt.usages.select_related("sector")}
    assert usages["Batteries"].share_percent == Decimal("60.00")
    assert all(u.source == "curated" for u in cobalt.usages.all())  # delete-then-insert
    assert cobalt.compositions.filter(product__slug="smartphone").exists()
