import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from commodities.models import Commodity, PriceQuote

pytestmark = pytest.mark.django_db


def client_for(username="a"):
    user = get_user_model().objects.create_user(username, f"{username}@e.com", "x")
    c = APIClient()
    c.force_authenticate(user)
    return c, user


@pytest.fixture
def alu():
    c = Commodity.objects.create(name="Aluminium", slug="aluminium")
    PriceQuote.objects.create(
        commodity=c, date=dt.date(2024, 6, 1),
        price_usd=Decimal("2500"), price_eur=Decimal("2300"), source="commodities_api",
    )
    return c


def make_portfolio(client, **over):
    body = {"name": "P", "base_currency": "EUR", "fee_percent": "0.20", "fee_fixed": "0"}
    body.update(over)
    return client.post("/api/portfolios/", body, format="json")


def test_requires_authentication():
    assert APIClient().get("/api/portfolios/").status_code in (401, 403)


def test_create_and_list_scoped_to_user(alu):
    ca, _ = client_for("a")
    cb, _ = client_for("b")
    r = make_portfolio(ca)
    assert r.status_code == 201
    pid = r.json()["id"]

    assert ca.get("/api/portfolios/").json()["count"] == 1
    assert ca.get("/api/portfolios/").json()["results"][0]["base_currency"] == "EUR"
    # user B sees nothing and cannot read A's portfolio
    assert cb.get("/api/portfolios/").json()["results"] == []
    assert cb.get(f"/api/portfolios/{pid}/").status_code == 404


def test_deposit_buy_and_valuation(alu):
    ca, _ = client_for("a")
    pid = make_portfolio(ca).json()["id"]
    base = f"/api/portfolios/{pid}"

    assert ca.post(f"{base}/transactions/", {"kind": "deposit", "date": "2024-06-01", "amount": "1000"}, format="json").status_code == 201
    r = ca.post(f"{base}/transactions/", {"kind": "buy", "date": "2024-06-01", "commodity": "aluminium", "amount": "500"}, format="json")
    assert r.status_code == 201
    assert float(r.json()["fee"]) == 1.0  # 0.2% of 500

    v = ca.get(f"{base}/valuation/?as_of=2024-06-01").json()
    assert float(v["cash"]) == 499.0
    assert v["currency"] == "EUR"
    assert len(v["positions"]) == 1
    assert v["positions"][0]["commodity"]["slug"] == "aluminium"


def test_buy_without_cash_returns_400(alu):
    ca, _ = client_for("a")
    pid = make_portfolio(ca).json()["id"]
    r = ca.post(f"/api/portfolios/{pid}/transactions/", {"kind": "buy", "date": "2024-06-01", "commodity": "aluminium", "amount": "500"}, format="json")
    assert r.status_code == 400
    assert "Trésorerie" in r.json()["detail"]


def test_preview_does_not_persist(alu):
    ca, _ = client_for("a")
    pid = make_portfolio(ca).json()["id"]
    base = f"/api/portfolios/{pid}"
    ca.post(f"{base}/transactions/", {"kind": "deposit", "date": "2024-06-01", "amount": "1000"}, format="json")
    r = ca.post(f"{base}/preview/", {"kind": "buy", "date": "2024-06-01", "commodity": "aluminium", "amount": "500"}, format="json")
    assert r.status_code == 200
    assert float(r.json()["fee"]) == 1.0
    assert float(r.json()["cash_after"]) == 499.0
    # nothing saved: only the deposit remains
    assert len(ca.get(f"{base}/transactions/").json()) == 1


def test_batch_buy(alu):
    Commodity.objects.create(name="Or", slug="or")  # second asset
    PriceQuote.objects.create(commodity=Commodity.objects.get(slug="or"), date=dt.date(2024, 6, 1),
                              price_usd=Decimal("2000"), price_eur=Decimal("1800"), source="commodities_api")
    ca, _ = client_for("a")
    pid = make_portfolio(ca).json()["id"]
    base = f"/api/portfolios/{pid}"
    ca.post(f"{base}/transactions/", {"kind": "deposit", "date": "2024-06-01", "amount": "1000"}, format="json")
    r = ca.post(f"{base}/transactions/batch/", {"items": [
        {"kind": "buy", "date": "2024-06-01", "commodity": "aluminium", "amount": "300"},
        {"kind": "buy", "date": "2024-06-01", "commodity": "or", "amount": "300"},
    ]}, format="json")
    assert r.status_code == 201
    assert len(r.json()) == 2
    v = ca.get(f"{base}/valuation/?as_of=2024-06-01").json()
    assert len(v["positions"]) == 2


def test_history_endpoint(alu):
    ca, _ = client_for("a")
    pid = make_portfolio(ca).json()["id"]
    base = f"/api/portfolios/{pid}"
    ca.post(f"{base}/transactions/", {"kind": "deposit", "date": "2024-06-01", "amount": "1000"}, format="json")
    ca.post(f"{base}/transactions/", {"kind": "buy", "date": "2024-06-01", "commodity": "aluminium", "amount": "500"}, format="json")
    pts = ca.get(f"{base}/history/?from=2024-06-01&to=2024-06-03&resolution=daily").json()
    assert len(pts) == 3
    # 1000 deposit − 1 fee (0.2% of 500) = 999 (cash 499 + position 500)
    assert float(pts[0]["value"]) == pytest.approx(999.0, abs=0.01)


def test_delete_transaction(alu):
    ca, _ = client_for("a")
    pid = make_portfolio(ca).json()["id"]
    base = f"/api/portfolios/{pid}"
    tid = ca.post(f"{base}/transactions/", {"kind": "deposit", "date": "2024-06-01", "amount": "1000"}, format="json").json()["id"]
    assert ca.delete(f"{base}/transactions/{tid}/").status_code == 204
    assert ca.get(f"{base}/transactions/").json() == []


def test_currency_frozen_after_first_transaction(alu):
    ca, _ = client_for("a")
    pid = make_portfolio(ca, base_currency="EUR").json()["id"]
    base = f"/api/portfolios/{pid}"
    ca.post(f"{base}/transactions/", {"kind": "deposit", "date": "2024-06-01", "amount": "1000"}, format="json")
    r = ca.patch(f"/api/portfolios/{pid}/", {"base_currency": "USD"}, format="json")
    assert r.status_code == 400
    assert "Devise" in str(r.json())
