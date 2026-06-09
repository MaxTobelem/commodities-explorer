import datetime as dt
from decimal import Decimal

import pytest
import responses

from commodities import services
from commodities.datasources.base import (
    CompositionRecord,
    EnrichmentProvider,
    EnrichmentResult,
    ImpactRecord,
    ProductionRecord,
    ReserveRecord,
    UsageRecord,
)
from commodities.datasources.gdelt import GDELT_DOC_API, GdeltProvider
from commodities.datasources.usgs import UsgsProvider
from commodities.models import (
    Commodity,
    CommodityProduction,
    CommodityUsage,
    Country,
    Event,
    EventImpact,
    ImportRun,
    Product,
    Sector,
)

pytestmark = pytest.mark.django_db


def make_cobalt():
    return Commodity.objects.create(name="Cobalt", slug="cobalt", symbol="LCO", price_symbol="LCO")


class FakeProvider(EnrichmentProvider):
    key = "fake"

    def __init__(self, commodity):
        self.commodity = commodity

    def fetch(self, commodities):
        c = self.commodity
        return EnrichmentResult(
            production=[ProductionRecord(c, "COD", "RD Congo", 2024, Decimal("130000"), "usgs")],
            reserves=[ReserveRecord(c, "COD", "RD Congo", 2024, Decimal("6000000"), "usgs")],
            usages=[UsageRecord(c, "Batteries", Decimal("70"), "", "rmis", nace_code="C27")],
            compositions=[CompositionRecord(c, "Smartphone", "Cathode", "rmis")],
            impacts=[
                ImpactRecord(
                    c, "Tensions en RD Congo (2024)", Event.Type.WAR, dt.date(2024, 1, 1),
                    "", "", EventImpact.Direction.UP, None, "gdelt",
                )
            ],
        )


def test_enrich_data_applies_records_and_tags_review(monkeypatch):
    cobalt = make_cobalt()
    monkeypatch.setattr(
        services, "get_enrichment_providers", lambda: [FakeProvider(cobalt)]
    )

    run = services.enrich_data()

    assert run.status == ImportRun.Status.SUCCESS
    # Core entities auto-created from natural keys
    assert Country.objects.filter(iso3="COD").exists()
    assert Sector.objects.filter(slug="batteries", nace_code="C27").exists()
    assert Product.objects.filter(slug="smartphone").exists()
    assert Event.objects.filter(slug="tensions-en-rd-congo-2024").exists()
    # Qualitative links flagged for review; quantitative not
    usage = CommodityUsage.objects.get(commodity=cobalt)
    assert usage.needs_review is True and usage.share_percent == Decimal("70.00")
    assert CommodityProduction.objects.get(commodity=cobalt).production_t == Decimal("130000.00")
    assert EventImpact.objects.get(commodity=cobalt).needs_review is True


def test_enrich_data_is_idempotent(monkeypatch):
    cobalt = make_cobalt()
    monkeypatch.setattr(services, "get_enrichment_providers", lambda: [FakeProvider(cobalt)])

    services.enrich_data()
    services.enrich_data()

    assert Sector.objects.count() == 1
    assert Event.objects.count() == 1
    assert CommodityUsage.objects.filter(commodity=cobalt).count() == 1


def test_enrich_data_isolates_provider_failure(monkeypatch):
    cobalt = make_cobalt()

    class Boom(EnrichmentProvider):
        key = "boom"

        def fetch(self, commodities):
            raise RuntimeError("network down")

    monkeypatch.setattr(
        services, "get_enrichment_providers", lambda: [Boom(), FakeProvider(cobalt)]
    )

    run = services.enrich_data()

    # The run still succeeds (good provider applied), failure is noted as a warning
    assert run.status == ImportRun.Status.SUCCESS
    assert "boom: RuntimeError" in run.message
    assert CommodityUsage.objects.filter(commodity=cobalt).count() == 1


@responses.activate
def test_gdelt_links_conflict_to_commodity_via_producer():
    cobalt = make_cobalt()
    drc = Country.objects.create(name="RD Congo", iso3="COD")
    CommodityProduction.objects.create(
        commodity=cobalt, country=drc, year=2024, production_t=Decimal("130000")
    )
    responses.add(
        responses.GET,
        GDELT_DOC_API,
        json={"articles": [{"title": f"Conflit {i}", "url": "http://x"} for i in range(12)]},
        status=200,
    )

    result = GdeltProvider().fetch([cobalt])

    assert len(result.impacts) == 1
    impact = result.impacts[0]
    assert impact.commodity == cobalt
    assert "RD Congo" in impact.event_title
    assert impact.direction == EventImpact.Direction.UP


@responses.activate
def test_gdelt_ignores_low_signal():
    cobalt = make_cobalt()
    drc = Country.objects.create(name="RD Congo", iso3="COD")
    CommodityProduction.objects.create(
        commodity=cobalt, country=drc, year=2024, production_t=Decimal("130000")
    )
    responses.add(responses.GET, GDELT_DOC_API, json={"articles": [{"title": "x"}]}, status=200)

    result = GdeltProvider().fetch([cobalt])

    assert result.impacts == []


def test_usgs_parses_production_csv():
    cobalt = make_cobalt()
    csv_text = "iso3,country,year,production_t\nCOD,RD Congo,2024,130000\nAUS,Australie,2024,5900\n"

    records = UsgsProvider.parse_production_csv(csv_text, cobalt)

    assert len(records) == 2
    assert records[0].country_iso3 == "COD"
    assert records[0].production_t == Decimal("130000")
    assert records[0].source == "usgs"
