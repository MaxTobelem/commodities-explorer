import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from commodities.models import Commodity, PriceQuote

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    c = APIClient()
    user = get_user_model().objects.create_user("u", "u@e.com", "x")
    c.force_authenticate(user)
    return c


@pytest.fixture
def seeded():
    call_command("seed")
    cobalt = Commodity.objects.get(slug="cobalt")
    PriceQuote.objects.create(
        commodity=cobalt,
        date=dt.date(2024, 6, 1),
        price_usd=Decimal("30000"),
        price_eur=Decimal("27000"),
        source="seed",
    )


def names(payload):
    return {c["name"] for c in payload["results"]}


def test_requires_authentication():
    r = APIClient().get("/api/commodities/")
    assert r.status_code in (401, 403)


def test_list_commodities(client, seeded):
    r = client.get("/api/commodities/")
    assert r.status_code == 200
    assert r.json()["count"] == 3
    assert {"Aluminium", "Cobalt", "Or"} <= names(r.json())


def test_detail_has_latest_price_annotation(client, seeded):
    body = client.get("/api/commodities/cobalt/").json()
    assert body["latest_price_usd"] == "30000.0000"
    assert body["latest_price_eur"] == "27000.0000"
    assert body["latest_price_date"] == "2024-06-01"


def test_filter_by_country(client, seeded):
    n = names(client.get("/api/commodities/?country=COD").json())
    assert n == {"Cobalt"}  # only cobalt is produced/held in DR Congo in the seed


def test_filter_by_sector(client, seeded):
    n = names(client.get("/api/commodities/?sector=batteries").json())
    assert n == {"Cobalt"}


def test_filter_by_product(client, seeded):
    n = names(client.get("/api/commodities/?product=smartphone").json())
    assert {"Cobalt", "Or"} <= n
    assert "Aluminium" not in n


def test_filter_by_event(client, seeded):
    n = names(client.get("/api/commodities/?event=tensions-dapprovisionnement-en-rdc").json())
    assert n == {"Cobalt"}


def test_filter_by_category(client, seeded):
    n = names(client.get("/api/commodities/?category=precious").json())
    assert n == {"Or"}


def test_subresource_production(client, seeded):
    rows = client.get("/api/commodities/cobalt/production/").json()
    assert any(row["country"]["iso3"] == "COD" for row in rows)


def test_subresource_prices_with_date_filter(client, seeded):
    rows = client.get("/api/commodities/cobalt/prices/?from=2024-01-01").json()
    assert len(rows) == 1
    assert rows[0]["price_usd"] == "30000.0000"


def test_countries_filtered_by_commodity(client, seeded):
    iso3s = {c["iso3"] for c in client.get("/api/countries/?commodity=cobalt").json()["results"]}
    assert "COD" in iso3s


def test_sectors_filtered_by_commodity(client, seeded):
    n = names(client.get("/api/sectors/?commodity=cobalt").json())
    assert "Batteries" in n


def test_event_detail_commodities(client, seeded):
    rows = client.get(
        "/api/events/tensions-dapprovisionnement-en-rdc/commodities/"
    ).json()
    assert any(row["commodity"]["slug"] == "cobalt" for row in rows)
