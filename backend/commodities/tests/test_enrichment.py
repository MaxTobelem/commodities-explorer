import datetime as dt
import io
import re
import zipfile
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
from commodities.datasources.gdelt import GDELT_EVENTS_URL, GdeltProvider
from commodities.datasources.owid import OWID_URL, OwidProvider
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


# --- GDELT (bulk daily Events export) --------------------------------------

GDELT_EVENTS_RE = re.compile(re.escape(GDELT_EVENTS_URL) + r"/\d{8}\.export\.CSV\.zip")


def _gdelt_row(action_fips, *, quad="4", root="19", articles="150", url="http://news/x",
               dateadded="20260611"):
    """One 58-field GDELT 1.0 Event record (tab-separated)."""
    row = [""] * 58
    row[1] = "20260101"  # SQLDATE
    row[28] = root  # EventRootCode
    row[29] = quad  # QuadClass (4 = material conflict)
    row[33] = articles  # NumArticles
    row[50] = f"Somewhere, {action_fips}"  # ActionGeo_FullName
    row[51] = action_fips  # ActionGeo_CountryCode (FIPS)
    row[56] = dateadded  # DATEADDED (= file day)
    row[57] = url  # SOURCEURL
    return "\t".join(row)


def _gdelt_zip(rows):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("20260611.export.CSV", "\n".join(rows) + "\n")
    return buf.getvalue()


def _producing(commodity, iso3, name):
    country = Country.objects.create(name=name, iso3=iso3)
    CommodityProduction.objects.create(
        commodity=commodity, country=country, year=2024, production_t=Decimal("130000")
    )
    return country


@responses.activate
def test_gdelt_flags_producer_country_in_material_conflict():
    cobalt = make_cobalt()
    _producing(cobalt, "COD", "RD Congo")  # FIPS CG → COD
    rows = [
        _gdelt_row("CG", root="19", articles="120"),  # armed clashes (most covered)
        _gdelt_row("CG", root="14", articles="40"),  # protests, same country
        _gdelt_row("CG", quad="1", articles="999"),  # cooperation → ignored
        _gdelt_row("US", root="19", articles="500"),  # not a producer here → ignored
    ]
    responses.add(responses.GET, GDELT_EVENTS_RE, body=_gdelt_zip(rows), status=200)

    result = GdeltProvider().fetch([cobalt])

    assert len(result.impacts) == 1
    impact = result.impacts[0]
    assert impact.commodity == cobalt
    assert "RD Congo" in impact.event_title
    assert impact.direction == EventImpact.Direction.UP
    assert impact.source_url == "http://news/x"
    assert "Affrontements armés" in impact.description  # root 19 = most-covered event
    assert "160 articles" in impact.description  # 120 + 40; cooperation row excluded


@responses.activate
def test_gdelt_ignores_low_conflict():
    cobalt = make_cobalt()
    _producing(cobalt, "COD", "RD Congo")
    responses.add(
        responses.GET, GDELT_EVENTS_RE, body=_gdelt_zip([_gdelt_row("CG", articles="20")]), status=200
    )

    assert GdeltProvider().fetch([cobalt]).impacts == []  # 20 < threshold (50 in tests)


@responses.activate
def test_gdelt_handles_missing_daily_file():
    cobalt = make_cobalt()
    _producing(cobalt, "COD", "RD Congo")
    responses.add(responses.GET, GDELT_EVENTS_RE, status=404)

    assert GdeltProvider().fetch([cobalt]).impacts == []  # missing file → no crash, no impact


@responses.activate
def test_gdelt_dates_event_from_dateadded():
    cobalt = make_cobalt()
    _producing(cobalt, "COD", "RD Congo")
    responses.add(
        responses.GET, GDELT_EVENTS_RE,
        body=_gdelt_zip([_gdelt_row("CG", articles="150", dateadded="20260610")]), status=200,
    )

    result = GdeltProvider().fetch([cobalt])

    assert result.impacts[0].start_date == dt.date(2026, 6, 10)  # ingest day, never Jan 1


@responses.activate
def test_refresh_events_applies_only_gdelt_impacts():
    cobalt = make_cobalt()
    _producing(cobalt, "COD", "RD Congo")
    responses.add(
        responses.GET, GDELT_EVENTS_RE,
        body=_gdelt_zip([_gdelt_row("CG", articles="150", dateadded="20260611")]), status=200,
    )

    run = services.refresh_events()

    assert run.status == ImportRun.Status.SUCCESS
    impact = EventImpact.objects.select_related("event").get(commodity=cobalt)
    assert impact.event.start_date == dt.date(2026, 6, 11)
    assert impact.event.source_url == "http://news/x"
    assert impact.needs_review is True


USGS_SAMPLE = (
    "SOURCE,COMMODITY,COUNTRY,TYPE,UNIT_MEAS,PROD_2023,PROD_EST_ 2024,PROD_NOTES,"
    "CAP_2023,CAP_EST_ 2024,CAP_NOTES,RESERVES_2024,RESERVE_NOTES\n"
    'MCS2025,Cobalt,Congo (Kinshasa),"Mine production, cobalt content",metric tons,210000,220000,,,,,6000000,\n'
    'MCS2025,Cobalt,Canada ,"Mine production, cobalt content",metric tons,4300,4500,,,,,220000,\n'
    'MCS2025,Cobalt,World total (rounded),"Mine production",metric tons,,240000,,,,,11000000,\n'
    'MCS2025,Aluminum,China,"Smelter production, aluminum",thousand metric tons,41000,43000,,,,,,\n'
    'MCS2025,Aluminum,Other Countries,"Smelter production, aluminum",thousand metric tons,,5000,,,,,,\n'
)


def test_usgs_parses_world_data():
    cobalt = make_cobalt()
    alu = Commodity.objects.create(name="Aluminium", slug="aluminium", price_symbol="ALU")
    wanted = {"Cobalt": cobalt, "Aluminum": alu}

    res = UsgsProvider.parse_world_data(USGS_SAMPLE, wanted)

    prod = {(r.commodity.slug, r.country_iso3): r for r in res.production}
    assert prod[("cobalt", "COD")].production_t == Decimal("220000.00")  # Congo (Kinshasa) → COD
    assert prod[("cobalt", "COD")].year == 2024
    assert prod[("cobalt", "CAN")].production_t == Decimal("4500.00")  # "Canada " (trailing space)
    assert prod[("aluminium", "CHN")].production_t == Decimal("43000000.00")  # thousand t → ×1000
    assert len(res.production) == 3  # aggregates (World total / Other Countries) skipped
    assert all(r.country_iso3 for r in res.production)

    reserves = {(r.commodity.slug, r.country_iso3): r for r in res.reserves}
    assert reserves[("cobalt", "COD")].reserves_t == Decimal("6000000.00")
    assert ("aluminium", "CHN") not in reserves  # aluminium reserves are reported as bauxite
    assert all(r.note == "Production minière" for r in res.production if r.commodity.slug == "cobalt")


USGS_STAGE_SAMPLE = (
    "SOURCE,COMMODITY,COUNTRY,TYPE,UNIT_MEAS,PROD_2023,PROD_EST_ 2024,PROD_NOTES,"
    "CAP_2023,CAP_EST_ 2024,CAP_NOTES,RESERVES_2024,RESERVE_NOTES\n"
    'MCS2025,Copper,Chile,"Mine production, recoverable",thousand metric tons,5000,5300,,,,,190000,\n'
    'MCS2025,Copper,China,"Mine production, recoverable",thousand metric tons,1700,1800,,,,,41000,\n'
    'MCS2025,Copper,China,"Refinery production",thousand metric tons,12000,12500,,,,,,\n'
)


def test_usgs_keeps_primary_stage_and_labels_it():
    copper = Commodity.objects.create(name="Cuivre", slug="cuivre", price_symbol="Copper")

    res = UsgsProvider.parse_world_data(USGS_STAGE_SAMPLE, {"Copper": copper})

    by_iso = {r.country_iso3: r for r in res.production}
    # Only the primary stage (mine) is kept; the 12.5 Mt refinery row is dropped.
    assert set(by_iso) == {"CHL", "CHN"}
    assert by_iso["CHN"].production_t == Decimal("1800000.00")  # mine, not refinery
    assert all(r.note == "Production minière" for r in res.production)


@responses.activate
def test_owid_production_latest_year_and_unit():
    wheat = Commodity.objects.create(name="Blé", slug="ble", price_symbol="Wheat, US HRW")
    body = (
        "entity,code,year,wheat__00000015__production__005510__tonnes\n"
        "China,CHN,2023,138000000\n"
        "China,CHN,2024,140000000\n"
        "World,OWID_WRL,2024,800000000\n"  # aggregate, must be skipped
        "India,IND,2024,113000000\n"
    )
    responses.add(
        responses.GET, OWID_URL.format(slug="wheat-production").split("?")[0], body=body, status=200
    )

    res = OwidProvider().fetch([wheat])

    by = {r.country_iso3: r for r in res.production}
    assert len(res.production) == 2  # CHN + IND (World aggregate skipped)
    assert by["CHN"].year == 2024  # latest year per country
    assert by["CHN"].production_t == Decimal("140000000.00")
    assert by["CHN"].unit == "t"


@responses.activate
def test_owid_reserves_for_energy_with_unit():
    oil = Commodity.objects.create(name="Pétrole", slug="petrole", price_symbol="Crude oil, Brent")
    # Oil is in both OWID production and reserves maps → mock both endpoints.
    responses.add(
        responses.GET,
        OWID_URL.format(slug="oil-production-by-country").split("?")[0],
        body="entity,code,year,oil_production__twh\nUnited States,USA,2020,9000\n",
        status=200,
    )
    responses.add(
        responses.GET,
        OWID_URL.format(slug="oil-proved-reserves").split("?")[0],
        body=(
            "entity,code,year,oil_reserves_t\n"
            "Saudi Arabia,SAU,2019,40000000000\n"
            "Saudi Arabia,SAU,2020,41000000000\n"
            "World,OWID_WRL,2020,236000000000\n"  # aggregate, skipped
        ),
        status=200,
    )

    res = OwidProvider().fetch([oil])

    assert len(res.reserves) == 1  # SAU latest year; World aggregate skipped
    reserve = res.reserves[0]
    assert reserve.country_iso3 == "SAU"
    assert reserve.year == 2020
    assert reserve.reserves_t == Decimal("41000000000.00")
    assert reserve.unit == "t"
