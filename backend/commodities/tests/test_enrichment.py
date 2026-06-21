import datetime as dt
import re
from decimal import Decimal

import pytest
import responses
from django.utils import timezone

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
from commodities.datasources.gnews import GOOGLE_NEWS_RSS, GoogleNewsProvider
from commodities.datasources.mining import MiningNewsProvider
from commodities.datasources.owid import OWID_URL, OwidProvider
from commodities.datasources.presse import PresseProvider
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


# --- Commodity news (Google News RSS) --------------------------------------

GNEWS_RE = re.compile(re.escape(GOOGLE_NEWS_RSS) + r".*")


def _rss(items):
    """Minimal Google News RSS body. items: (title, link, pubDate, source)."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?><rss><channel>']
    for title, link, pub, source in items:
        parts.append(
            f"<item><title>{title}</title><link>{link}</link>"
            f"<pubDate>{pub}</pubDate><source url='http://x'>{source}</source></item>"
        )
    parts.append("</channel></rss>")
    return "".join(parts).encode("utf-8")


@responses.activate
def test_gnews_builds_events_from_real_headlines():
    cobalt = make_cobalt()
    items = [
        ("Le cours du cobalt flambe sur fond de pénurie - Les Echos", "http://a",
         "Fri, 12 Jun 2026 08:00:00 GMT", "Les Echos"),
        ("Cobalt : la RDC bloque une mine - RFI", "http://b",
         "Thu, 11 Jun 2026 08:00:00 GMT", "RFI"),
    ]
    responses.add(responses.GET, GNEWS_RE, body=_rss(items), status=200)

    result = GoogleNewsProvider().fetch([cobalt])

    assert len(result.impacts) == 2
    top = result.impacts[0]  # most recent first
    assert top.commodity == cobalt
    assert top.event_title == "Le cours du cobalt flambe sur fond de pénurie"  # " - source" stripped
    assert top.event_type == Event.Type.ECONOMIC
    assert top.source_url == "http://a"
    assert top.source == "gnews"
    assert top.direction == EventImpact.Direction.UP  # "flambe" / "pénurie"
    assert "Les Echos" in top.description


@responses.activate
def test_gnews_reads_direction_else_neutral():
    cobalt = make_cobalt()
    items = [
        ("Les prix du cobalt reculent fortement - X", "http://d", "Fri, 12 Jun 2026 08:00:00 GMT", "X"),
        ("Le marché du cobalt reste stable - Y", "http://n", "Thu, 11 Jun 2026 08:00:00 GMT", "Y"),
    ]
    responses.add(responses.GET, GNEWS_RE, body=_rss(items), status=200)

    by_url = {im.source_url: im for im in GoogleNewsProvider().fetch([cobalt]).impacts}

    assert by_url["http://d"].direction == EventImpact.Direction.DOWN  # "reculent"
    assert by_url["http://n"].direction == EventImpact.Direction.NEUTRAL  # no signal → no fake direction


@responses.activate
def test_gnews_caps_one_article_per_source():
    cobalt = make_cobalt()
    items = [
        ("Cobalt prix jour 1 - Spam", "http://1", "Fri, 12 Jun 2026 08:00:00 GMT", "Spam"),
        ("Cobalt prix jour 2 - Spam", "http://2", "Thu, 11 Jun 2026 08:00:00 GMT", "Spam"),
        ("Cobalt : la production rebondit - Le Monde", "http://3", "Wed, 10 Jun 2026 08:00:00 GMT", "Le Monde"),
    ]
    responses.add(responses.GET, GNEWS_RE, body=_rss(items), status=200)

    impacts = GoogleNewsProvider().fetch([cobalt]).impacts

    assert len(impacts) == 2  # only one of the two "Spam" articles kept
    assert any("Le Monde" in im.description for im in impacts)


@responses.activate
def test_gnews_filters_off_topic_noise():
    cobalt = make_cobalt()
    items = [
        ("Un smartphone au cobalt présenté au salon - X", "http://noise",
         "Fri, 12 Jun 2026 08:00:00 GMT", "X"),
        ("Le cours du cobalt grimpe - Les Echos", "http://ok",
         "Fri, 12 Jun 2026 08:00:00 GMT", "Les Echos"),
    ]
    responses.add(responses.GET, GNEWS_RE, body=_rss(items), status=200)

    urls = [im.source_url for im in GoogleNewsProvider().fetch([cobalt]).impacts]

    assert urls == ["http://ok"]  # off-topic headline (no market signal) is dropped


@responses.activate
def test_gnews_categorizes_by_headline():
    cobalt = make_cobalt()
    items = [
        ("La guerre fait flamber les cours du cobalt - A", "http://w", "Fri, 12 Jun 2026 08:00:00 GMT", "A"),
        ("Sécheresse : la production de cobalt menacée - B", "http://d", "Thu, 11 Jun 2026 08:00:00 GMT", "B"),
        ("Nouveaux droits de douane sur le cobalt - C", "http://p", "Wed, 10 Jun 2026 08:00:00 GMT", "C"),
        ("Les cours du cobalt en hausse - D", "http://e", "Tue, 09 Jun 2026 08:00:00 GMT", "D"),
    ]
    responses.add(responses.GET, GNEWS_RE, body=_rss(items), status=200)

    by_url = {im.source_url: im.event_type for im in GoogleNewsProvider().fetch([cobalt]).impacts}

    assert by_url["http://w"] == Event.Type.WAR
    assert by_url["http://d"] == Event.Type.DISASTER
    assert by_url["http://p"] == Event.Type.POLICY
    assert by_url["http://e"] == Event.Type.ECONOMIC


@responses.activate
def test_gnews_isolates_failure():
    cobalt = make_cobalt()
    responses.add(responses.GET, GNEWS_RE, status=404)

    assert GoogleNewsProvider().fetch([cobalt]).impacts == []  # no crash, no events


@responses.activate
def test_refresh_events_replaces_news_and_purges_legacy():
    cobalt = make_cobalt()
    # A legacy GDELT "Tensions en…" event that the refresh must purge.
    legacy = Event.objects.create(
        title="Tensions en RD Congo (2026)", slug="tensions-en-rd-congo-2026", type=Event.Type.WAR
    )
    EventImpact.objects.create(
        event=legacy, commodity=cobalt, source="gdelt", direction=EventImpact.Direction.UP
    )
    items = [("Le cobalt grimpe en flèche - Les Echos", "http://a",
              "Fri, 12 Jun 2026 08:00:00 GMT", "Les Echos")]
    responses.add(responses.GET, GNEWS_RE, body=_rss(items), status=200)

    run = services.refresh_events()

    assert run.status == ImportRun.Status.SUCCESS
    assert not Event.objects.filter(slug="tensions-en-rd-congo-2026").exists()  # legacy purged
    impact = EventImpact.objects.select_related("event").get(commodity=cobalt)
    assert impact.event.type == Event.Type.ECONOMIC
    assert impact.event.source_url == "http://a"
    assert impact.source == "gnews" and impact.needs_review is True


def test_refresh_events_stores_long_google_news_url(monkeypatch):
    # Google News redirect links are base64 blobs that exceed any CharField limit;
    # source_url is a TextField so the whole URL round-trips (regression: it used
    # to be URLField(1000) and one long link aborted the entire daily refresh).
    cobalt = make_cobalt()
    long_url = "https://news.google.com/rss/articles/" + "A" * 1500

    class P(EnrichmentProvider):
        key = "gnews"

        def fetch(self, commodities):
            return EnrichmentResult(impacts=[
                ImpactRecord(cobalt, "Cobalt en hausse", Event.Type.ECONOMIC,
                             dt.date(2026, 6, 1), "desc", long_url,
                             EventImpact.Direction.UP, None, "gnews")
            ])

    monkeypatch.setattr(services, "get_enrichment_providers", lambda: [P()])

    run = services.refresh_events()

    assert run.status == ImportRun.Status.SUCCESS
    stored = Event.objects.get(slug="cobalt-en-hausse").source_url
    assert stored == long_url and len(stored) > 1000  # stored whole, not truncated


def test_refresh_events_skips_corrupt_record_and_keeps_the_rest(monkeypatch):
    # A single pathological article must never abort the whole news refresh
    # (per-record savepoint). The bad record (null title → NOT NULL violation) is
    # dropped and counted; the good ones are saved and the run still succeeds.
    cobalt = make_cobalt()
    good = ImpactRecord(cobalt, "Cobalt en hausse", Event.Type.ECONOMIC, dt.date(2026, 6, 1),
                        "desc", "http://ok", EventImpact.Direction.UP, None, "presse")
    bad = ImpactRecord(cobalt, None, Event.Type.ECONOMIC, dt.date(2026, 6, 1),
                       "x", "http://bad", EventImpact.Direction.NEUTRAL, None, "presse")

    class P(EnrichmentProvider):
        key = "presse"

        def fetch(self, commodities):
            return EnrichmentResult(impacts=[good, bad])

    monkeypatch.setattr(services, "get_enrichment_providers", lambda: [P()])

    run = services.refresh_events()

    assert run.status == ImportRun.Status.SUCCESS
    assert Event.objects.filter(slug="cobalt-en-hausse").exists()  # good one survived
    assert EventImpact.objects.count() == 1
    assert "1 ignorée" in run.message


def test_refresh_events_keeps_recent_news_purges_beyond_retention(monkeypatch):
    # Rolling 31-day archive: pre-existing news no longer in any feed survives if
    # it's within the window, and is purged once it's older.
    cobalt = make_cobalt()
    today = timezone.now().date()
    recent = Event.objects.create(
        title="Actu d'il y a 10 jours", slug="actu-recente",
        type=Event.Type.ECONOMIC, start_date=today - dt.timedelta(days=10),
    )
    EventImpact.objects.create(
        event=recent, commodity=cobalt, source="presse", direction=EventImpact.Direction.UP
    )
    old = Event.objects.create(
        title="Actu d'il y a 40 jours", slug="actu-vieille",
        type=Event.Type.ECONOMIC, start_date=today - dt.timedelta(days=40),
    )
    EventImpact.objects.create(
        event=old, commodity=cobalt, source="presse", direction=EventImpact.Direction.UP
    )

    class P(EnrichmentProvider):
        key = "presse"

        def fetch(self, commodities):  # a fresh article (triggers the purge path)
            return EnrichmentResult(impacts=[
                ImpactRecord(cobalt, "Actu du jour", Event.Type.ECONOMIC, today,
                             "d", "http://x", EventImpact.Direction.UP, None, "presse")
            ])

    monkeypatch.setattr(services, "get_enrichment_providers", lambda: [P()])

    run = services.refresh_events()

    assert run.status == ImportRun.Status.SUCCESS
    assert Event.objects.filter(slug="actu-recente").exists()       # within 31 j → kept
    assert not Event.objects.filter(slug="actu-vieille").exists()   # beyond 31 j → purged
    assert Event.objects.filter(slug="actu-du-jour").exists()       # fresh one inserted


# --- Commodity news (publisher RSS — presse) --------------------------------


def _presse_rss(items):
    """Minimal publisher RSS body. items: (title, link, pubDate, description)."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?><rss><channel>']
    for title, link, pub, desc in items:
        parts.append(
            f"<item><title>{title}</title><link>{link}</link>"
            f"<pubDate>{pub}</pubDate><description>{desc}</description></item>"
        )
    parts.append("</channel></rss>")
    return "".join(parts).encode("utf-8")


def _make_petrole():
    return Commodity.objects.create(
        name="Pétrole brut (Brent)", slug="petrole-brut-brent", price_symbol="Crude oil, Brent"
    )


@responses.activate
def test_presse_builds_event_with_real_description(settings):
    settings.PRESSE_FEEDS = [("Terre-net", "http://feed")]
    ble = Commodity.objects.create(name="Blé (US HRW)", slug="ble-us-hrw", price_symbol="Wheat")
    chapo = "Le blé Euronext retombe sous les 200 €/t après les pluies annoncées sur les bassins."
    responses.add(
        responses.GET, "http://feed",
        body=_presse_rss([
            ("Le blé Euronext retombe sur les 200 €/t", "http://art",
             "Fri, 12 Jun 2026 08:00:00 GMT", chapo)
        ]),
        status=200,
    )

    impacts = PresseProvider().fetch([ble]).impacts

    assert len(impacts) == 1
    im = impacts[0]
    assert im.commodity == ble
    assert im.event_title == "Le blé Euronext retombe sur les 200 €/t"
    assert im.source == "presse" and im.source_url == "http://art"
    assert chapo in im.description and "Terre-net" in im.description  # real summary + attribution
    assert im.direction == EventImpact.Direction.DOWN  # "retombe"
    assert im.event_type == Event.Type.ECONOMIC


@responses.activate
def test_presse_requires_commodity_in_title(settings):
    settings.PRESSE_FEEDS = [("X", "http://feed")]
    ble = Commodity.objects.create(name="Blé (US HRW)", slug="ble-us-hrw", price_symbol="W")
    responses.add(
        responses.GET, "http://feed",
        body=_presse_rss([
            ("Les marchés agricoles dans le rouge", "http://a", "Fri, 12 Jun 2026 08:00:00 GMT",
             "Le blé et le maïs reculent à Chicago.")
        ]),
        status=200,
    )

    # "blé" appears only in the body, not the title → not attached (avoids drift).
    assert PresseProvider().fetch([ble]).impacts == []


@responses.activate
def test_presse_drops_non_market_titles(settings):
    settings.PRESSE_FEEDS = [("X", "http://feed")]
    ble = Commodity.objects.create(name="Blé (US HRW)", slug="ble-us-hrw", price_symbol="W")
    responses.add(
        responses.GET, "http://feed",
        body=_presse_rss([
            ("Comment limiter le piétin-échaudage en blé dur", "http://a",
             "Fri, 12 Jun 2026 08:00:00 GMT", "Conseils agronomiques pour la culture du blé dur.")
        ]),
        status=200,
    )

    # Agronomy how-to: names the commodity but carries no market signal → dropped.
    assert PresseProvider().fetch([ble]).impacts == []


@responses.activate
def test_presse_categorizes_and_links_multiple_commodities(settings):
    settings.PRESSE_FEEDS = [("Connaissance des Énergies", "http://feed")]
    petrole = _make_petrole()
    soja = Commodity.objects.create(name="Soja", slug="soja", price_symbol="Soybeans")
    responses.add(
        responses.GET, "http://feed",
        body=_presse_rss([
            ("Guerre en Iran : le pétrole flambe et entraîne le soja", "http://w",
             "Fri, 12 Jun 2026 08:00:00 GMT", "Les cours s'envolent après l'attaque ; le soja suit.")
        ]),
        status=200,
    )

    impacts = PresseProvider().fetch([petrole, soja]).impacts

    # One article about two commodities → two impacts sharing one event.
    assert {im.commodity.slug for im in impacts} == {"petrole-brut-brent", "soja"}
    assert all(im.event_type == Event.Type.WAR for im in impacts)  # "guerre"
    assert all(im.direction == EventImpact.Direction.UP for im in impacts)  # "flambe"/"s'envole"
    assert len({im.event_title for im in impacts}) == 1


@responses.activate
def test_presse_caps_and_dedups_per_commodity(settings):
    settings.PRESSE_FEEDS = [("X", "http://feed")]
    settings.PRESSE_MAX_PER_COMMODITY = 2
    petrole = _make_petrole()
    body = _presse_rss([
        ("Le cours du pétrole grimpe encore", "http://1", "Fri, 12 Jun 2026 08:00:00 GMT",
         "Le baril progresse fortement aujourd'hui sur le marché."),
        ("Le cours du pétrole grimpe encore", "http://dup", "Thu, 11 Jun 2026 08:00:00 GMT",
         "Doublon de titre, autre lien."),
        ("Le prix du pétrole se stabilise", "http://2", "Wed, 10 Jun 2026 08:00:00 GMT",
         "Le baril fait une pause après la hausse récente."),
        ("Le baril recule nettement", "http://3", "Tue, 09 Jun 2026 08:00:00 GMT",
         "Le pétrole perd du terrain sur le marché mondial."),
    ])
    responses.add(responses.GET, "http://feed", body=body, status=200)

    impacts = PresseProvider().fetch([petrole]).impacts

    assert len(impacts) == 2  # capped at 2, most recent first, duplicate title dropped
    assert impacts[0].source_url == "http://1"
    assert "http://dup" not in {im.source_url for im in impacts}


@responses.activate
def test_presse_isolates_feed_failure(settings):
    settings.PRESSE_FEEDS = [("Bad", "http://bad"), ("Good", "http://good")]
    petrole = _make_petrole()
    responses.add(responses.GET, "http://bad", status=404)
    responses.add(
        responses.GET, "http://good",
        body=_presse_rss([
            ("Le prix du pétrole grimpe", "http://ok", "Fri, 12 Jun 2026 08:00:00 GMT",
             "Le baril monte nettement ce matin sur le marché.")
        ]),
        status=200,
    )

    impacts = PresseProvider().fetch([petrole]).impacts

    assert [im.source_url for im in impacts] == ["http://ok"]  # bad feed isolated, good one kept


@responses.activate
def test_refresh_events_presse_primary_gnews_fallback(settings):
    settings.PRESSE_FEEDS = [("Connaissance des Énergies", "http://presse")]
    petrole = _make_petrole()
    cobalt = make_cobalt()
    responses.add(
        responses.GET, "http://presse",
        body=_presse_rss([
            ("Le prix du pétrole grimpe sur fond de tensions", "http://oil",
             "Fri, 12 Jun 2026 08:00:00 GMT",
             "Le baril de Brent progresse nettement après les annonces de l'Opep.")
        ]),
        status=200,
    )
    responses.add(
        responses.GET, GNEWS_RE,
        body=_rss([("Le cours du cobalt recule - RFI", "http://co",
                    "Fri, 12 Jun 2026 08:00:00 GMT", "RFI")]),
        status=200,
    )

    run = services.refresh_events()

    assert run.status == ImportRun.Status.SUCCESS
    oil = EventImpact.objects.select_related("event").get(commodity=petrole)
    assert oil.source == "presse" and "Brent progresse" in oil.event.description  # real summary
    assert EventImpact.objects.get(commodity=cobalt).source == "gnews"  # gap filled by fallback
    assert not EventImpact.objects.filter(commodity=petrole, source="gnews").exists()  # no double-fetch


# --- Commodity news (English mining feeds — mining) -------------------------


def _make_cuivre():
    return Commodity.objects.create(name="Cuivre", slug="cuivre", price_symbol="Copper")


@responses.activate
def test_mining_builds_metal_event_with_english_description(settings):
    settings.MINING_FEEDS = [("Mining.com", "http://mine")]
    cuivre = _make_cuivre()
    chapo = "Copper futures climbed to a record high in London as a widening supply deficit hit the market."
    responses.add(
        responses.GET, "http://mine",
        body=_presse_rss([
            ("Copper hits record high on supply deficit", "http://c",
             "Fri, 12 Jun 2026 08:00:00 GMT", chapo)
        ]),
        status=200,
    )

    impacts = MiningNewsProvider().fetch([cuivre]).impacts

    assert len(impacts) == 1
    im = impacts[0]
    assert im.commodity == cuivre and im.source == "mining"
    assert im.event_title == "Copper hits record high on supply deficit"
    assert chapo in im.description and "Mining.com" in im.description  # real EN summary + attribution
    assert im.direction == EventImpact.Direction.UP  # "record high" / "deficit"
    assert im.source_url == "http://c"


@responses.activate
def test_mining_requires_metal_in_title(settings):
    settings.MINING_FEEDS = [("X", "http://mine")]
    cuivre = _make_cuivre()
    responses.add(
        responses.GET, "http://mine",
        body=_presse_rss([
            ("Markets rally on rate-cut hopes", "http://a", "Fri, 12 Jun 2026 08:00:00 GMT",
             "Copper and gold prices rose with the broader market.")
        ]),
        status=200,
    )

    # metal named only in the body, not the title → not attached.
    assert MiningNewsProvider().fetch([cuivre]).impacts == []


@responses.activate
def test_mining_lead_pattern_ignores_the_verb(settings):
    settings.MINING_FEEDS = [("X", "http://mine")]
    cuivre = _make_cuivre()
    plomb = Commodity.objects.create(name="Plomb", slug="plomb", price_symbol="Lead")
    responses.add(
        responses.GET, "http://mine",
        body=_presse_rss([
            ("Copper miner leads a $2bn supply expansion", "http://c",
             "Fri, 12 Jun 2026 08:00:00 GMT", "The producer will lead new supply to the market.")
        ]),
        status=200,
    )

    impacts = MiningNewsProvider().fetch([cuivre, plomb]).impacts

    assert [im.commodity.slug for im in impacts] == ["cuivre"]  # "leads"/"lead" ≠ the metal lead


@responses.activate
def test_mining_isolates_feed_failure(settings):
    settings.MINING_FEEDS = [("Bad", "http://bad"), ("Good", "http://good")]
    cuivre = _make_cuivre()
    responses.add(responses.GET, "http://bad", status=404)
    responses.add(
        responses.GET, "http://good",
        body=_presse_rss([
            ("Copper price jumps on supply squeeze", "http://ok",
             "Fri, 12 Jun 2026 08:00:00 GMT", "Prices rose on mine disruptions.")
        ]),
        status=200,
    )

    assert [im.source_url for im in MiningNewsProvider().fetch([cuivre]).impacts] == ["http://ok"]


@responses.activate
def test_mining_translates_title_and_summary_to_french(settings, monkeypatch):
    settings.MINING_FEEDS = [("Mining.com", "http://mine")]
    settings.MINING_TRANSLATE = True
    from commodities.datasources import mining as mining_mod

    # Fake the translator (no network): tag each string so we can assert it was used.
    monkeypatch.setattr(mining_mod, "_translate_fr", lambda texts: {t: f"[fr] {t}" for t in texts})
    cuivre = _make_cuivre()
    responses.add(
        responses.GET, "http://mine",
        body=_presse_rss([
            ("Copper price jumps on supply deficit", "http://c", "Fri, 12 Jun 2026 08:00:00 GMT",
             "Copper rallied on a widening supply deficit and falling stockpiles today.")
        ]),
        status=200,
    )

    im = MiningNewsProvider().fetch([cuivre]).impacts[0]

    assert im.event_title == "[fr] Copper price jumps on supply deficit"  # title translated
    assert im.description.startswith("[fr] Copper rallied")  # summary translated
    assert im.direction == EventImpact.Direction.UP  # scored on English, before translation


@responses.activate
def test_refresh_events_mining_covers_metals_gnews_fills_rest(settings):
    settings.MINING_FEEDS = [("Mining.com", "http://mine")]
    cuivre = _make_cuivre()
    cobalt = make_cobalt()
    responses.add(
        responses.GET, "http://mine",
        body=_presse_rss([
            ("Copper price jumps to record on supply deficit", "http://cu",
             "Fri, 12 Jun 2026 08:00:00 GMT",
             "Copper rallied on a widening deficit and falling exchange stockpiles.")
        ]),
        status=200,
    )
    responses.add(
        responses.GET, GNEWS_RE,
        body=_rss([("Le cours du cobalt recule - RFI", "http://co",
                    "Fri, 12 Jun 2026 08:00:00 GMT", "RFI")]),
        status=200,
    )

    run = services.refresh_events()

    assert run.status == ImportRun.Status.SUCCESS
    cu = EventImpact.objects.select_related("event").get(commodity=cuivre)
    assert cu.source == "mining" and "Copper rallied" in cu.event.description  # real EN summary
    assert EventImpact.objects.get(commodity=cobalt).source == "gnews"  # gap filled by fallback
    assert not EventImpact.objects.filter(commodity=cuivre, source="gnews").exists()


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
