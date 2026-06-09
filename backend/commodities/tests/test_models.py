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
